"""Usage service — computes spend summary from DB rows."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai4i_core.ppu import get_inference_unit_map
from app.core.exceptions import EntityNotFoundError
from app.repositories.pay_per_use.usage_repository import UsageRepository
from app.utils.billing_month import shift_billing_month
from app.schemas.pay_per_use.usage import (
    SpendItem,
    TaskTypeUsage,
    TenantBudget,
    TenantHierarchicalItem,
    TenantHierarchicalListResponse,
    TenantUsageCount,
    TierUsageBreakdown,
    UsageSummaryResponse,
)

_UNIT_LABELS: dict[str, str] = get_inference_unit_map()
_CURRENCY = "INR"
_FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)


class _TenantTierBudget(NamedTuple):
    """Merges a tenant's most-recently-used tier this billing_month (from
    ppu_quota_usage) with their budget figures (from ppu_tenant_tier_assignments,
    read purely for budget_limit/available_balance — see get_tenant_budgets).
    """
    tenant_id: str
    tier_id: str
    tier_name: str
    budget_limit: Decimal
    available_balance: Decimal


def _tier_key(tier_id) -> str:
    """Canonical string key for a tier_id, including the null ("unassigned"/deleted
    tier) case — the single source of truth for matching a usage row's tier_id
    against an assignment's, so the two can never drift into comparing "None" against
    "unassigned" again (see _build_hierarchical_item's current_tier_row lookup)."""
    return str(tier_id) if tier_id is not None else "unassigned"


def _resolve_tier_name(tier_id, tier_names: dict) -> str:
    if tier_id is None:
        return "Unassigned"
    return tier_names.get(str(tier_id), "Unassigned")


def _resolve_budget(tenant_id: str, budgets_by_tenant: dict) -> tuple[Decimal, Decimal, bool]:
    """(budget_limit, available_balance, has_budget) for a tenant.

    has_budget is False when no ppu_tenant_tier_assignments row covers this billing
    month's end (see get_tenant_budgets) — the exact gap case this redesign exists to
    handle correctly. budget_limit/available_balance default to 0 in that case so
    display code has a concrete number to show, but has_budget is what callers must
    check before treating "no budget on file" as "exceeded a budget of 0" — those are
    different things (unknown vs. genuinely zero). The single place this default is
    applied, so tenant-list/detail and the summary card can't drift into disagreeing
    about what a missing budget row means (see get_summary's budget_exceeded count).
    """
    budget = budgets_by_tenant.get(tenant_id)
    if budget is None:
        return Decimal("0"), Decimal("0"), False
    return _to_decimal(budget.budget_limit), _to_decimal(budget.available_balance), True


def _merge_tier_and_budget(tier_rows, budgets_by_tenant: dict, tier_names: dict) -> list[_TenantTierBudget]:
    merged = []
    for row in tier_rows:
        budget_limit, available_balance, _ = _resolve_budget(row.tenant_id, budgets_by_tenant)
        merged.append(_TenantTierBudget(
            tenant_id=row.tenant_id,
            tier_id=_tier_key(row.tier_id),
            tier_name=_resolve_tier_name(row.tier_id, tier_names),
            budget_limit=budget_limit,
            available_balance=available_balance,
        ))
    return merged


def _to_decimal(value) -> Decimal:
    """Money/quota columns are Numeric in the DB; this codebase does all such arithmetic
    in Decimal end-to-end (tenant_assignment_service.py, the billing consumer) to avoid
    float rounding error compounding across sums. str(value) avoids importing an
    existing float's own binary-rounding artifacts into the Decimal."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _prev_month(billing_month: str) -> str:
    year, month = shift_billing_month(billing_month, -1)
    return f"{year:04d}-{month:02d}"


def _group_usage_by_tier(usage_rows, tier_names: dict) -> dict[str, dict]:
    """Groups flat (tier_id, inference_name) usage rows into {tier_key: {tierName, rows}}."""
    groups: dict[str, dict] = {}
    for row in usage_rows:
        tier_key = _tier_key(row.tier_id)
        bucket = groups.setdefault(
            tier_key, {"tierName": _resolve_tier_name(row.tier_id, tier_names), "rows": []}
        )
        bucket["rows"].append(row)
    return groups


def _build_hierarchical_item(
    assignment,
    tenant_name: str,
    usage_rows,
    model_task_type: str | None = None,
    tier_order: dict[str, datetime] | None = None,
    tier_names: dict | None = None,
) -> TenantHierarchicalItem:
    """Builds one tenant's hierarchical usage item from their end-of-period tier assignment
    plus their flat per-(tier, inference_name) usage rows for the billing month.

    spend/budget/tierBreakdown always reflect the tenant's FULL period totals across every
    tier they held that month — model_task_type never narrows these, it only controls the
    flat `usage` quota-bar fields (see below). tierBreakdown is ordered oldest-tier-first
    per tier_order (falls back to insertion order for any tier_key missing from it).

    The `usage` block shows one task type's numbers when model_task_type is explicitly
    passed, OR automatically when the tenant only has one distinct task type this period
    (nothing to disambiguate). consumed/spend are summed across every tier that type was
    used under, but quotaLimit is taken ONLY from the row under the tenant's CURRENT
    (end-of-period) tier — quotas aren't cumulative across tiers the way spend is; e.g.
    tier1 grants 500 tokens (100 used) then reassignment to tier2 grants 100 more (50 used)
    nets quotaLimit=100 (tier2's own grant), consumed=150 (100+50 summed).
    """
    tier_groups = _group_usage_by_tier(usage_rows, tier_names or {})
    ordered_tier_keys = sorted(
        tier_groups.keys(),
        key=lambda k: (tier_order or {}).get(k) or _FAR_FUTURE,
    )

    # First pass: build each tier's task-type rows and subtotal, and the tenant's grand
    # total across every tier. Percentage (each task's share) can only be computed once
    # the grand total is known — it's a share of the WHOLE tenant, not of its own tier's
    # subtotal, so a tenant who changed tiers mid-period would otherwise get percentages
    # that sum to 100% per tier group instead of 100% overall.
    tier_raw: list[dict] = []
    distinct_task_types: set[str] = set()
    tenant_spend = Decimal("0")

    for tier_key in ordered_tier_keys:
        bucket = tier_groups[tier_key]
        raw_task_types: list[dict] = []
        tier_spend = Decimal("0")
        for row in bucket["rows"]:
            units = _to_decimal(row.total_units)
            spend = round(_to_decimal(row.total_cost), 2)
            quota = _to_decimal(row.quota_snap) if row.quota_snap is not None else None
            remaining = round(max(Decimal("0"), quota - units), 2) if quota is not None else None
            raw_task_types.append({
                "taskType": row.inference_name,
                "unit": _UNIT_LABELS.get(row.inference_name, row.inference_name),
                "quotaLimit": quota,
                "consumed": units,
                "remaining": remaining,
                "spend": spend,
            })
            tier_spend += spend
            distinct_task_types.add(row.inference_name)

        tier_raw.append({
            "tierId": tier_key,
            "tierName": bucket["tierName"],
            "spend": tier_spend,
            "raw_task_types": raw_task_types,
        })
        tenant_spend += tier_spend

    tenant_spend = round(tenant_spend, 2)

    tier_breakdown: list[TierUsageBreakdown] = [
        TierUsageBreakdown(
            tierId=tg["tierId"],
            tierName=tg["tierName"],
            spend=round(tg["spend"], 2),
            taskTypes=[
                TaskTypeUsage(
                    **t,
                    percentage=round(t["spend"] / tenant_spend * 100, 1) if tenant_spend > 0 else Decimal("0"),
                )
                for t in tg["raw_task_types"]
            ],
        )
        for tg in tier_raw
    ]
    budget_limit = round(_to_decimal(assignment.budget_limit), 2)
    remaining_budget = round(_to_decimal(assignment.available_balance), 2)
    percentage_used = round(tenant_spend / budget_limit * 100, 1) if budget_limit > 0 else Decimal("0")

    effective_task_type = model_task_type
    if effective_task_type is None and len(distinct_task_types) == 1:
        effective_task_type = next(iter(distinct_task_types))

    # Multiple task types with nothing to disambiguate (no filter, no single-type
    # auto-detect): matches the old flat TenantUsageItem.quotaUnit contract, which was
    # always a concrete string and fell back to "Units" here rather than leaving it unset.
    usage_count = TenantUsageCount(taskTypeCount=len(distinct_task_types), unit="Units")
    if effective_task_type:
        matching_rows = [r for r in usage_rows if r.inference_name == effective_task_type]
        total_consumed = sum((_to_decimal(r.total_units) for r in matching_rows), Decimal("0"))
        current_tier_row = next(
            (r for r in matching_rows if _tier_key(r.tier_id) == assignment.tier_id), None
        )
        quota = (
            _to_decimal(current_tier_row.quota_snap)
            if current_tier_row is not None and current_tier_row.quota_snap is not None
            else None
        )
        if quota is None:
            percentage = Decimal("0")
        elif quota == 0:
            # A 0 quota is a deliberate "blocked for this cycle" tier setting (see
            # tier_service.py), not missing data — any usage against it is fully
            # exhausted, not 0% used.
            percentage = Decimal("100") if total_consumed > 0 else Decimal("0")
        else:
            percentage = round(total_consumed / quota * 100, 1)

        usage_count = TenantUsageCount(
            taskTypeCount=len(distinct_task_types),
            unit=_UNIT_LABELS.get(effective_task_type, effective_task_type),
            quotaLimit=round(quota, 2) if quota is not None else None,
            consumed=round(total_consumed, 2),
            remaining=round(max(Decimal("0"), quota - total_consumed), 2) if quota is not None else None,
            percentage=percentage,
        )

    return TenantHierarchicalItem(
        tenantId=assignment.tenant_id,
        tenantName=tenant_name,
        tier=assignment.tier_name,
        tierId=str(assignment.tier_id),
        currency=_CURRENCY,
        spend=tenant_spend,
        budget=TenantBudget(
            limit=budget_limit,
            spent=tenant_spend,
            remaining=remaining_budget,
            percentageUsed=percentage_used,
        ),
        usage=usage_count,
        tierBreakdown=tier_breakdown,
    )


def _tenant_spend_from_rows(usage_rows) -> Decimal:
    """Same rounding order _build_hierarchical_item uses for a tenant's total spend
    (round each row, sum, round again) — so sorting on this cheap pre-aggregate always
    agrees with the `spend` value the full hierarchical build would produce, without
    needing tier grouping or the rest of that build for tenants that get paginated out.
    """
    return round(
        sum((round(_to_decimal(row.total_cost), 2) for row in usage_rows), Decimal("0")), 2
    )


async def _resolve_tenant_names(
    tenant_ids: list[str], auth_db: Optional[AsyncSession]
) -> dict[str, str]:
    if not auth_db or not tenant_ids:
        return {}
    numeric = [int(t) for t in tenant_ids if t and t.isdigit()]
    if not numeric:
        return {}
    try:
        rows = await auth_db.execute(
            text("SELECT id, organisation FROM tenants WHERE id = ANY(:ids)"),
            {"ids": numeric},
        )
        return {str(r[0]): r[1] for r in rows.all()}
    except Exception as exc:
        logger.warning("Auth DB lookup failed — tenant names will show as IDs: %s", exc)
        return {}


class UsageService:
    def __init__(self, repo: UsageRepository) -> None:
        self._repo = repo

    async def _tenant_assignments_and_usage(
        self, billing_month: str, tier_id: str | None, task_types: list[str] | None = None
    ):
        """Tenants with at least one ppu_quota_usage row this billing_month, scoped to
        tier_id if given (their most-recently-active tier that month), plus their usage
        rows for that month — the same tenant-selection rule used by
        get_tenant_list/get_tenant_detail, so a tier + billing_period filter combination
        gives consistent results across all three endpoints. Note: these rows carry
        tier info only, NOT budget — callers that need budget_limit/available_balance
        must separately call get_tenant_budgets. ``task_types`` (from the caller) filters
        both queries to those task types at the SQL level.
        """
        tier_rows = await self._repo.get_tenants_with_usage_tier(
            billing_month, tier_id, task_types=task_types
        )
        tenant_ids = [row.tenant_id for row in tier_rows]
        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
            billing_month, tenant_ids, task_types=task_types
        )
        return tier_rows, usage_rows

    async def get_summary(
        self,
        billing_month: str,
        tier_id: str | None = None,
        task_types: list[str] | None = None,
    ) -> UsageSummaryResponse:
        """``task_types`` (from the frontend) filters the spend to those task types at
        the query level; tier_id narrows which tenants are counted.
        """
        assignments, usage_rows = await self._tenant_assignments_and_usage(
            billing_month, tier_id, task_types
        )

        by_task_type: dict[str, dict] = {}
        cost_by_tenant: dict[str, Decimal] = {}
        for row in usage_rows:
            units = _to_decimal(row.total_units)
            cost = _to_decimal(row.total_cost)
            bucket = by_task_type.setdefault(
                row.inference_name,
                {"unit": _UNIT_LABELS.get(row.inference_name, row.inference_name), "units": Decimal("0"), "cost": Decimal("0")},
            )
            bucket["units"] += units
            bucket["cost"] += cost
            cost_by_tenant[row.tenant_id] = cost_by_tenant.get(row.tenant_id, Decimal("0")) + cost

        total_spend = sum((b["cost"] for b in by_task_type.values()), Decimal("0"))

        # Quota allocated per task type, summed across tenants' CURRENT tier only (not
        # summed across every tier a tenant held that month) — same reasoning as
        # _build_hierarchical_item's current_tier_row: a quota grant resets on
        # reassignment, it isn't cumulative. Keyed by task type rather than gated to a
        # single one in scope, so it generalizes to however many are actually present.
        current_tier_by_tenant = {a.tenant_id: _tier_key(a.tier_id) for a in assignments}
        allocated_by_task_type: dict[str, Decimal] = {}
        for row in usage_rows:
            if row.quota_snap is None:
                continue
            if current_tier_by_tenant.get(row.tenant_id) != _tier_key(row.tier_id):
                continue
            allocated_by_task_type[row.inference_name] = (
                allocated_by_task_type.get(row.inference_name, Decimal("0")) + _to_decimal(row.quota_snap)
            )

        spend_items = [
            SpendItem(
                modelTaskType=name,
                unit=b["unit"],
                consumption=b["units"],
                allocated=round(allocated_by_task_type[name], 2) if name in allocated_by_task_type else None,
                spend=round(b["cost"], 2),
                percentage=round(b["cost"] / total_spend * 100, 1) if total_spend > 0 else Decimal("0"),
            )
            for name, b in by_task_type.items()
        ]
        spend_items.sort(key=lambda i: i.spend, reverse=True)

        active_tenants = len(assignments)
        tenant_ids = [a.tenant_id for a in assignments]
        budgets = await self._repo.get_tenant_budgets(billing_month, tenant_ids)
        # A tenant with no budget row on file has an unknown limit, not a limit of 0 —
        # they must not count as "exceeded" just for having any spend at all. This keeps
        # the summary card consistent with the tenant list/detail view, which shows the
        # same tenant at 0% used (see _resolve_budget) rather than "over budget."
        budget_exceeded = 0
        total_allocated_budget = Decimal("0")
        total_remaining_budget = Decimal("0")
        for a in assignments:
            budget_limit, available_balance, has_budget = _resolve_budget(a.tenant_id, budgets)
            if has_budget:
                total_allocated_budget += budget_limit
                total_remaining_budget += available_balance
                if cost_by_tenant.get(a.tenant_id, Decimal("0")) > budget_limit:
                    budget_exceeded += 1

        prev_month = _prev_month(billing_month)
        if tier_id:
            # tier_id scopes by tenant ("who was most recently on this tier that month"),
            # not by usage row, so it needs the full tenant-resolution pipeline to stay
            # consistent with the current month's figure above.
            _, prev_usage_rows = await self._tenant_assignments_and_usage(
                prev_month, tier_id, task_types
            )
            prev_total_spend = sum(
                (_to_decimal(row.total_cost) for row in prev_usage_rows), Decimal("0")
            )
        else:
            # No tenant scoping needed, so skip tenant/tier resolution entirely and get
            # the same number from one lightweight aggregate query (task-type filtered).
            prev_total_spend = _to_decimal(
                await self._repo.get_total_cost_for_month()
            )
        spend_change_percent = (
            round((total_spend - prev_total_spend) / prev_total_spend * 100, 1)
            if prev_total_spend > 0
            else None
        )

        return UsageSummaryResponse(
            billingPeriod=billing_month,
            totalSpend=round(total_spend, 2),
            currency=_CURRENCY,
            activeTenants=active_tenants,
            budgetExceededTenants=budget_exceeded,
            spendChangePercent=spend_change_percent,
            spendByModelTaskType=spend_items,
            totalAllocatedBudget=round(total_allocated_budget, 2),
            totalRemainingBudget=round(total_remaining_budget, 2),
        )

    async def get_tenant_list(
        self,
        billing_month: str,
        tier_id: str | None,
        model_task_type: str | None,
        auth_db: Optional[AsyncSession],
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
        task_types: list[str] | None = None,
    ) -> TenantHierarchicalListResponse:
        """Hierarchical tenant usage: tenant -> tier(s) held during billing_month -> task types.

        Only tenants with at least one ppu_quota_usage row this billing_month appear —
        a tenant with a budget/tier assignment but zero usage that month is omitted
        entirely, not shown as a zero-usage row. The tenant-level `tier` reflects
        whichever tier they were most recently active under that month (derived from
        usage, not from ppu_tenant_tier_assignments — see get_tenants_with_usage_tier).
        `budget` is a separate lookup into ppu_tenant_tier_assignments, read purely for
        budget_limit/available_balance as of the END of billing_month. tierBreakdown
        covers every tier the tenant actually had usage under that month, oldest first —
        a mid-month tier change surfaces as two entries.

        model_task_type does NOT filter which tenants appear, nor narrow their spend/budget/
        tierBreakdown — those always reflect the full period. It only populates the flat
        `usage` quota-bar fields with that one task type's numbers (see _build_hierarchical_item).

        limit/offset paginate the sorted list; `total` in the response is the full matching
        tenant count (before slicing), not the page size, so callers can compute page count.

        Sorting/pagination happen BEFORE the per-tenant hierarchical build (tier grouping,
        quota/percentage calcs, tier_first_seen, tenant-name resolution, budget lookup) —
        that build only runs for the tenants on the requested page, not the full matching
        tenant list, via a cheap spend pre-aggregate (_tenant_spend_from_rows) computed
        straight from the already-fetched usage rows.
        """
        assignments = await self._repo.get_tenants_with_usage_tier(
            billing_month, tier_id, task_types=task_types
        )
        total = len(assignments)
        if not assignments:
            return TenantHierarchicalListResponse(data=[], total=0)

        tenant_ids = [row.tenant_id for row in assignments]
        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
            billing_month, tenant_ids, task_types=task_types
        )

        usage_by_tenant: dict[str, list] = {}
        for row in usage_rows:
            usage_by_tenant.setdefault(row.tenant_id, []).append(row)

        # tenant_id as a secondary key breaks spend ties deterministically — without it,
        # tenants tied on spend (e.g. many at 0) could sort differently between two
        # sequential paginated calls, duplicating a tenant across pages or dropping one
        # entirely, even with the repository's own ORDER BY as a first line of defense.
        assignments.sort(
            key=lambda a: (_tenant_spend_from_rows(usage_by_tenant.get(a.tenant_id, [])), a.tenant_id),
            reverse=(sort_order != "asc"),
        )
        page_assignments = assignments[offset : offset + limit]

        page_tenant_ids = [a.tenant_id for a in page_assignments]

        async def _fetch_page_data():
            tier_first_seen = await self._repo.get_tier_first_seen(page_tenant_ids)
            budgets = await self._repo.get_tenant_budgets(billing_month, page_tenant_ids)
            tier_names = await self._repo.get_tier_names()
            return tier_first_seen, budgets, tier_names

        # _resolve_tenant_names runs on auth_db, a separate session from self._db — the
        # three self._db calls above must stay sequential (an AsyncSession can't run
        # concurrent queries), but that whole group has no dependency on auth_db, so it
        # runs concurrently with it instead of after it.
        (tier_first_seen, budgets, tier_names), org_map = await asyncio.gather(
            _fetch_page_data(),
            _resolve_tenant_names(page_tenant_ids, auth_db),
        )

        order_by_tenant: dict[str, dict[str, datetime]] = {}
        for row in tier_first_seen:
            order_by_tenant.setdefault(row.tenant_id, {})[str(row.tier_id)] = row.first_seen

        merged_page = _merge_tier_and_budget(page_assignments, budgets, tier_names)

        items = [
            _build_hierarchical_item(
                assignment,
                org_map.get(assignment.tenant_id, assignment.tenant_id),
                usage_by_tenant.get(assignment.tenant_id, []),
                model_task_type,
                order_by_tenant.get(assignment.tenant_id),
                tier_names,
            )
            for assignment in merged_page
        ]

        return TenantHierarchicalListResponse(data=items, total=total)

    async def get_tenant_detail(
        self,
        tenant_id: str,
        billing_month: str,
        auth_db: Optional[AsyncSession],
        task_types: list[str] | None = None,
    ) -> TenantHierarchicalItem:
        """Same hierarchical shape as get_tenant_list, scoped to a single tenant — the
        tenant's `tier` reflects whichever tier they were most recently active under
        this billing_month (derived from ppu_quota_usage, not ppu_tenant_tier_assignments
        — see get_tenants_with_usage_tier), `budget` is a separate lookup into
        ppu_tenant_tier_assignments for budget_limit/available_balance as of the
        billing_month's lookup instant (now, if it's the current month; end of
        month otherwise — see get_tenant_budgets/_budget_lookup_instant), and
        tierBreakdown covers every tier they had usage under that month, oldest
        first.

        Unlike get_tenant_list, a tenant with zero ppu_quota_usage rows this
        billing_month is NOT omitted here — it falls into the zero-value branch
        below, so single-tenant lookups keep returning something for a valid
        tenant with no usage yet this period. `tier`/`tierId` in that branch
        still reflect the tenant's actual current assignment (read from
        ppu_tenant_tier_assignments, at the same lookup instant get_tenant_budgets
        uses elsewhere) — falling back to "Unassigned" only when even that
        assignment doesn't exist.
        """
        assignments = await self._repo.get_tenants_with_usage_tier(
            billing_month, tenant_id=tenant_id, task_types=task_types
        )
        if not assignments:
            # No usage this period is a valid tenant configuration (not an error) —
            # surface a zero-value item so the UI can render an empty state instead of
            # a 404. But an empty `assignments` also comes back for a tenant_id that
            # doesn't exist at all (no existence check upstream), so confirm the tenant
            # is real before treating this as the unassigned case — otherwise a
            # typo'd/deleted tenant_id would silently look like a legitimate empty state
            # instead of a 404. When auth_db isn't available we can't verify either way,
            # so fall back to trusting tenant_id (matches _resolve_tenant_names' own
            # no-auth_db behavior elsewhere).
            org_map = await _resolve_tenant_names([tenant_id], auth_db)
            if auth_db is not None and tenant_id not in org_map:
                raise EntityNotFoundError(f"Tenant {tenant_id}")

            # No usage to derive a tier from, but the tenant may still have a live
            # tier assignment (e.g. just onboarded, hasn't made any calls yet) — show
            # that instead of "Unassigned" so the tier isn't blank for no reason.
            budgets = await self._repo.get_tenant_budgets(billing_month, [tenant_id])
            budget_row = budgets.get(tenant_id)
            if budget_row is not None:
                tier_names = await self._repo.get_tier_names()
                tier_id = _tier_key(budget_row.tier_id)
                tier_name = _resolve_tier_name(budget_row.tier_id, tier_names)
            else:
                tier_id = "unassigned"
                tier_name = "Unassigned"

            # A tenant with a live assignment but no usage yet this period still has a
            # real allocated/remaining budget — budget.limit/remaining must not collapse
            # to 0 just because there's nothing to build a hierarchical item from
            # (previously it did, even with a real budget_limit/available_balance on file).
            budget_limit, available_balance, _ = _resolve_budget(tenant_id, budgets)
            budget_limit = round(budget_limit, 2)
            available_balance = round(available_balance, 2)

            return TenantHierarchicalItem(
                tenantId=tenant_id,
                tenantName=org_map.get(tenant_id, tenant_id),
                tier=tier_name,
                tierId=tier_id,
                currency=_CURRENCY,
                spend=Decimal("0"),
                budget=TenantBudget(
                    limit=budget_limit,
                    spent=Decimal("0"),
                    remaining=available_balance,
                    percentageUsed=Decimal("0"),
                ),
                usage=TenantUsageCount(taskTypeCount=0),
                tierBreakdown=[],
            )

        async def _fetch_tenant_data():
            usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
                billing_month, [tenant_id], task_types=task_types
            )
            tier_first_seen = await self._repo.get_tier_first_seen([tenant_id])
            budgets = await self._repo.get_tenant_budgets(billing_month, [tenant_id])
            tier_names = await self._repo.get_tier_names()
            return usage_rows, tier_first_seen, budgets, tier_names

        # Same reasoning as get_tenant_list: the self._db calls stay sequential among
        # themselves, but run concurrently with the auth_db-backed name resolution.
        (usage_rows, tier_first_seen, budgets, tier_names), org_map = await asyncio.gather(
            _fetch_tenant_data(),
            _resolve_tenant_names([tenant_id], auth_db),
        )
        tier_order = {str(row.tier_id): row.first_seen for row in tier_first_seen}
        assignment = _merge_tier_and_budget(assignments, budgets, tier_names)[0]

        return _build_hierarchical_item(
            assignment, org_map.get(tenant_id, tenant_id), usage_rows, None, tier_order, tier_names
        )
