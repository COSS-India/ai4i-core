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
from app.utils.billing_month import current_billing_month
from app.schemas.pay_per_use.usage import (
    SpendItem,
    TaskTypeUsage,
    TenantBudget,
    TenantBudgetDetail,
    TenantHierarchicalItem,
    TenantHierarchicalListResponse,
    TenantUsageCount,
    TenantUsageDetailResponse,
    TierUsageBreakdown,
    UsageSummaryResponse,
)

_UNIT_LABELS: dict[str, str] = get_inference_unit_map()
_CURRENCY = "INR"
_FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)


class _TenantTierBudget(NamedTuple):
    """Merges a tenant's most-recently-used tier this billing_month (from
    ppu_quota_usage) with their budget figures — reconstructed by
    get_tenant_budgets from tenants.allocated_budget minus budget_usage spend
    (ppu_tenant_tier_assignments, the old source, was dropped in AI4IDS-2923).
    """
    tenant_id: str
    tier_id: str
    tier_name: str
    budget_limit: Decimal
    available_balance: Decimal
    # Real, tenant-total spend — sum of budget_usage.api_key_budget_used across this
    # tenant's api keys (see get_tenant_budgets), always lifetime-cumulative. 0 for a
    # tenant with no budget row on file (unknown, not genuinely zero — see
    # _resolve_spent).
    spent: Decimal = Decimal("0")
    # Set once at tenant creation (tenants.budget_effective_from/to, auth-service),
    # untouched by budget top-up/top-down — None for a tenant with no configured
    # window. Only /usage-tenant's response surfaces these (see TenantBudgetDetail).
    budget_effective_from: Optional[datetime] = None
    budget_effective_to: Optional[datetime] = None


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

    has_budget is False when the tenant is absent from get_tenant_budgets' result —
    unknown tenant_id, auth_db unavailable, or found but with allocated_budget still
    NULL (never configured) — the exact gap case this redesign exists to handle
    correctly. budget_limit/available_balance default to 0 in that case so
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


def _resolve_spent(tenant_id: str, budgets_by_tenant: dict) -> Decimal:
    """Real, tenant-total spend — 0 for a tenant absent from get_tenant_budgets'
    result (unknown, same "unknown vs. genuinely zero" convention _resolve_budget
    already applies to budget_limit/available_balance; there is no has_budget-style
    flag here because a tenant can only be absent from that dict for the same
    reasons _resolve_budget already documents, and 0 spend either way is the
    correct thing to display)."""
    budget = budgets_by_tenant.get(tenant_id)
    if budget is None:
        return Decimal("0")
    return _to_decimal(budget.spent)


def _merge_tier_and_budget(tier_rows, budgets_by_tenant: dict, tier_names: dict) -> list[_TenantTierBudget]:
    merged = []
    for row in tier_rows:
        budget_limit, available_balance, _ = _resolve_budget(row.tenant_id, budgets_by_tenant)
        budget_row = budgets_by_tenant.get(row.tenant_id)
        merged.append(_TenantTierBudget(
            tenant_id=row.tenant_id,
            tier_id=_tier_key(row.tier_id),
            tier_name=_resolve_tier_name(row.tier_id, tier_names),
            budget_limit=budget_limit,
            available_balance=available_balance,
            spent=_resolve_spent(row.tenant_id, budgets_by_tenant),
            budget_effective_from=budget_row.budget_effective_from if budget_row else None,
            budget_effective_to=budget_row.budget_effective_to if budget_row else None,
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


def _task_type_key(row):
    """Stable identity for a usage row's task type.

    The catalogue id when the row has one. Rows written before the catalogue
    existed carry NULL, so they fall back to their stored name — otherwise every
    legacy row would collapse into one ``None`` bucket and be counted as a single
    task type.
    """
    return row.inference_type_id if row.inference_type_id is not None else row.task_type


def _row_unit(row) -> str:
    """Billing unit for a usage row.

    The catalogue column comes free on the join and is authoritative. It is NULL
    only for pre-catalogue rows, which fall back to the bundled unit map and then
    to echoing the name — the behaviour this had before the join existed.
    """
    return getattr(row, "task_type_unit", None) or _UNIT_LABELS.get(
        row.task_type, row.task_type
    )


def _effective_unit(matching_rows, fallback_name: str | None) -> str:
    """Unit for the single-task-type `usage` block."""
    for row in matching_rows:
        return _row_unit(row)
    if fallback_name is None:
        return "Units"
    return _UNIT_LABELS.get(fallback_name, fallback_name)


def _group_usage_by_tier(usage_rows, tier_names: dict) -> dict[str, dict]:
    """Groups flat (tier_id, inference type) usage rows into {tier_key: {tierName, rows}}."""
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
    quota_usage_rows=None,
    model_task_type_id: int | None = None,
    tier_order: dict[str, datetime] | None = None,
    tier_names: dict | None = None,
) -> TenantHierarchicalItem:
    """Builds one tenant's hierarchical usage item from their end-of-period tier assignment
    plus their flat per-(tier, inference type) usage rows for the billing month.

    budget/tierBreakdown always reflect the tenant's FULL period totals across every
    tier they held that month — model_task_type_id never narrows these, it only controls the
    flat `usage` quota-bar fields (see below). tierBreakdown is ordered oldest-tier-first
    per tier_order (falls back to insertion order for any tier_key missing from it).

    spend/budget.spent/budget.percentageUsed come from `assignment.spent` (real,
    tenant-total spend — sum of budget_usage.api_key_budget_used, see
    get_tenant_budgets/_resolve_spent), NOT from these usage rows — ppu_quota_usage
    has no per-task-type/per-tier money column (see get_tenant_tier_usage_breakdown's
    docstring), so tierBreakdown/taskTypes carry no spend field at all; only the
    tenant-total figure is real.

    The `usage` block shows one task type's numbers when model_task_type_id is explicitly
    passed, OR automatically when the tenant only has one distinct task type this period
    (nothing to disambiguate). consumed is summed across every tier that type was used
    under, but quotaLimit is taken ONLY from the row under the tenant's CURRENT
    (end-of-period) tier — quotas aren't cumulative across tiers; e.g. tier1 grants 500
    tokens (100 used) then reassignment to tier2 grants 100 more (50 used) nets
    quotaLimit=100 (tier2's own grant), consumed=150 (100+50 summed).

    quota_usage_rows is the row set the `usage` block's consumed/quotaLimit/remaining/
    percentage are computed from — separate from usage_rows (which drives tierBreakdown)
    because quota resets monthly while tierBreakdown is meant to go all-time when the
    caller passes billing_month=None. Reusing usage_rows for quota too in that case
    would divide a lifetime `consumed` by a single month's `quotaLimit`, e.g. 6 months
    of normal usage reporting ~600%. Defaults to usage_rows when the caller doesn't pass
    it (billing_month scoped to one month already, where the two row sets are identical).
    """
    if quota_usage_rows is None:
        quota_usage_rows = usage_rows
    tier_groups = _group_usage_by_tier(usage_rows, tier_names or {})
    ordered_tier_keys = sorted(
        tier_groups.keys(),
        key=lambda k: (tier_order or {}).get(k) or _FAR_FUTURE,
    )

    # Identity is the catalogue id; the name is only ever a display value. Legacy
    # rows carry a NULL id, so they key on their own name to stay distinct from
    # each other rather than collapsing into a single None bucket.
    distinct_task_types: set = set()
    type_names: dict = {}
    tier_breakdown: list[TierUsageBreakdown] = []
    for tier_key in ordered_tier_keys:
        bucket = tier_groups[tier_key]
        task_types: list[TaskTypeUsage] = []
        for row in bucket["rows"]:
            units = _to_decimal(row.total_units)
            quota = _to_decimal(row.quota_snap) if row.quota_snap is not None else None
            remaining = round(max(Decimal("0"), quota - units), 2) if quota is not None else None
            key = _task_type_key(row)
            task_types.append(TaskTypeUsage(
                taskType=row.task_type,
                unit=_row_unit(row),
                quotaLimit=quota,
                consumed=units,
                remaining=remaining,
            ))
            distinct_task_types.add(key)
            type_names[key] = row.task_type

        tier_breakdown.append(TierUsageBreakdown(
            tierId=tier_key,
            tierName=bucket["tierName"],
            taskTypes=task_types,
        ))

    tenant_spend = round(_to_decimal(assignment.spent), 2)
    budget_limit = round(_to_decimal(assignment.budget_limit), 2)
    remaining_budget = round(_to_decimal(assignment.available_balance), 2)
    percentage_used = round(tenant_spend / budget_limit * 100, 1) if budget_limit > 0 else Decimal("0")

    effective_key = model_task_type_id
    if effective_key is None and len(distinct_task_types) == 1:
        effective_key = next(iter(distinct_task_types))

    # Multiple task types with nothing to disambiguate (no filter, no single-type
    # auto-detect): matches the old flat TenantUsageItem.quotaUnit contract, which was
    # always a concrete string and fell back to "Units" here rather than leaving it unset.
    usage_count = TenantUsageCount(taskTypeCount=len(distinct_task_types), unit="Units")
    if effective_key is not None:
        matching_rows = [r for r in quota_usage_rows if _task_type_key(r) == effective_key]
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
            unit=_effective_unit(matching_rows, type_names.get(effective_key)),
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


def _to_tenant_usage_detail(
    item: TenantHierarchicalItem,
    budget_effective_from: datetime | None = None,
    budget_effective_to: datetime | None = None,
) -> TenantUsageDetailResponse:
    """/usage-tenant's response shape: identical to TenantHierarchicalItem — budget
    carries the tenant's configured budget window on top (see TenantBudgetDetail),
    passed in separately since TenantHierarchicalItem's own budget field never
    carries it. tierBreakdown needs no reshaping any more: TierUsageBreakdown/
    TaskTypeUsage carry no spend/percentage at either endpoint (see their own
    docstrings), so /usage-tenants and /usage-tenant now share the identical shape."""
    return TenantUsageDetailResponse(
        tenantId=item.tenantId,
        tenantName=item.tenantName,
        tier=item.tier,
        tierId=item.tierId,
        currency=item.currency,
        spend=item.spend,
        budget=TenantBudgetDetail(
            limit=item.budget.limit,
            spent=item.budget.spent,
            remaining=item.budget.remaining,
            percentageUsed=item.budget.percentageUsed,
            budgetEffectiveFrom=budget_effective_from,
            budgetEffectiveTo=budget_effective_to,
        ),
        usage=item.usage,
        tierBreakdown=item.tierBreakdown,
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
        # A raising query leaves auth_db's transaction aborted; every caller
        # here reuses this same session afterward (get_tenant_budgets, which
        # does NOT swallow its own errors by design — see its docstring), so
        # without this rollback a degraded-but-recoverable name lookup would
        # turn the next, unrelated query into an uncaught PendingRollbackError.
        # The rollback itself is best-effort too — it must never turn this
        # already-degraded path into a harder failure than the one it's
        # recovering from.
        try:
            await auth_db.rollback()
        except Exception:
            logger.warning("Auth DB rollback after failed lookup also failed", exc_info=True)
        return {}


class UsageService:
    def __init__(self, repo: UsageRepository) -> None:
        self._repo = repo

    async def _tenant_assignments_and_usage(
        self, billing_month: str | None, tier_id: str | None, task_type_ids: list[int] | None = None
    ):
        """Tenants with at least one ppu_quota_usage row in scope, scoped to
        tier_id if given (their most-recently-active tier in scope), plus their usage
        rows in scope — the same tenant-selection rule used by
        get_tenant_list/get_tenant_detail, so a tier + billing_period filter combination
        gives consistent results across all three endpoints. billing_month=None means
        all-time (no month filter), i.e. usage up to now. Note: these rows carry
        tier info only, NOT budget — callers that need budget_limit/available_balance
        must separately call get_tenant_budgets. ``task_type_ids`` (from the caller) filters
        both queries to those task types at the SQL level.
        """
        tier_rows = await self._repo.get_tenants_with_usage_tier(
            billing_month, tier_id, task_type_ids=task_type_ids
        )
        tenant_ids = [row.tenant_id for row in tier_rows]
        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
            billing_month, tenant_ids, task_type_ids=task_type_ids
        )
        return tier_rows, usage_rows

    async def get_summary(
        self,
        billing_month: str | None,
        tier_id: str | None = None,
        task_type_ids: list[int] | None = None,
        auth_db: Optional[AsyncSession] = None,
    ) -> UsageSummaryResponse:
        """``task_type_ids`` (from the frontend) filters consumption/allocated to those
        task types at the query level; tier_id narrows which tenants are counted.
        totalSpend/budgetExceededTenants are real (sum of budget_usage.
        api_key_budget_used, see get_tenant_budgets) and always lifetime-cumulative —
        billing_month does NOT scope them, only which tenants/usage rows are in scope
        for consumption/allocated/activeTenants (budget_usage has no per-month
        dimension, same reason budget/available_balance are always current-balance
        everywhere else in this service).

        billing_month=None means all-time usage up to now (no month filter) for
        consumption/allocated/tier figures; billingPeriod is null in that case (not a
        sentinel string like "lifetime") so a caller that echoes it back as this or a
        sibling endpoint's billing_period query param gets a value that's actually
        valid there — omitted, meaning all-time again — instead of a 422
        (billing_period is validated against ^\d{4}-(0[1-9]|1[0-2])$ on every
        /usage-* route). There is no month-over-month spendChangePercent field —
        removed entirely rather than kept as a permanently-null one, since there's
        no per-month money breakdown to ever compare, regardless of billing_month
        (see UsageSummaryResponse's own docstring).

        auth_db is optional (defaults to None, matching every existing caller/test
        that predates get_tenant_budgets needing cross-DB access) — without it,
        budget/spend/remaining figures degrade to 0 the same way a tenant with no
        budget on file already does (see _resolve_budget/_resolve_spent), rather than
        raising.
        """
        assignments, usage_rows = await self._tenant_assignments_and_usage(
            billing_month, tier_id, task_type_ids
        )

        by_task_type: dict[str, dict] = {}
        for row in usage_rows:
            units = _to_decimal(row.total_units)
            bucket = by_task_type.setdefault(
                _task_type_key(row),
                {"name": row.task_type, "unit": _row_unit(row), "units": Decimal("0")},
            )
            bucket["units"] += units

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
            allocated_by_task_type[_task_type_key(row)] = (
                allocated_by_task_type.get(_task_type_key(row), Decimal("0")) + _to_decimal(row.quota_snap)
            )

        # Keyed by catalogue id, but modelTaskType stays the name string the API
        # has always returned.
        spend_items = [
            SpendItem(
                modelTaskType=b["name"],
                unit=b["unit"],
                consumption=b["units"],
                allocated=round(allocated_by_task_type[key], 2) if key in allocated_by_task_type else None,
            )
            for key, b in by_task_type.items()
        ]
        # No spend field to sort by any more (see SpendItem's docstring) — consumption
        # (real usage volume) is the closest meaningful substitute for "biggest first".
        spend_items.sort(key=lambda i: i.consumption, reverse=True)

        active_tenants = len(assignments)
        tenant_ids = [a.tenant_id for a in assignments]
        budgets = await self._repo.get_tenant_budgets(billing_month, tenant_ids, auth_db)
        # Real, tenant-total spend (sum of budget_usage.api_key_budget_used) — always
        # lifetime-cumulative, since budget_usage carries no per-month dimension (see
        # get_tenant_budgets' own docstring). billing_month therefore no longer scopes
        # totalSpend/budgetExceededTenants, same as it already never scoped budget/
        # available_balance.
        total_spend = sum(
            (_resolve_spent(a.tenant_id, budgets) for a in assignments), Decimal("0")
        )
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
                if _resolve_spent(a.tenant_id, budgets) > budget_limit:
                    budget_exceeded += 1

        return UsageSummaryResponse(
            billingPeriod=billing_month,
            totalSpend=round(total_spend, 2),
            currency=_CURRENCY,
            activeTenants=active_tenants,
            budgetExceededTenants=budget_exceeded,
            spendByModelTaskType=spend_items,
            totalAllocatedBudget=round(total_allocated_budget, 2),
            totalRemainingBudget=round(total_remaining_budget, 2),
        )

    async def get_tenant_list(
        self,
        billing_month: str | None,
        tier_id: str | None,
        model_task_type_id: int | None,
        auth_db: Optional[AsyncSession],
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
        task_type_ids: list[int] | None = None,
    ) -> TenantHierarchicalListResponse:
        """Hierarchical tenant usage: tenant -> tier(s) held during billing_month -> task types.
        spend/budget/tierBreakdown are ALWAYS all-time (usage up to now) — billing_month
        never narrows them, whether it's given or omitted, since budget is a lifetime
        pool, not a monthly figure. The `usage` block's quota fields (quotaLimit/
        consumed/remaining/percentage) are the only thing billing_month controls: that
        month's data when given, else the current calendar month — never all-time,
        since quota resets monthly and isn't cumulative (see _build_hierarchical_item's
        quota_usage_rows docstring). billing_month still separately narrows which
        tenants appear at all (via get_tenants_with_usage_tier, below) and their
        tier-derived `tier` field, independent of this spend/quota split.

        Only tenants with at least one ppu_quota_usage row in scope (per billing_month,
        or all-time if omitted) appear — a tenant with a budget/tier assignment but no
        usage in scope is omitted entirely, not shown as a zero-usage row. The
        tenant-level `tier` reflects whichever tier they were most recently active
        under in that same scope, derived from usage (see get_tenants_with_usage_tier),
        not from a separate assignment table. `budget` is a separate lookup via
        get_tenant_budgets, reconstructed from tenants.allocated_budget minus
        budget_usage spend — this is always the tenant's CURRENT balance (budget_usage
        has no per-billing-month dimension; see get_tenant_budgets' own docstring).
        tierBreakdown covers every tier the tenant has ever had usage under (oldest
        first) — a tier change surfaces as two entries.

        model_task_type_id does NOT filter which tenants appear, nor narrow their spend/budget/
        tierBreakdown — those always reflect the full period. It only populates the flat
        `usage` quota-bar fields with that one task type's numbers (see _build_hierarchical_item).

        limit/offset paginate the sorted list; `total` in the response is the full matching
        tenant count (before slicing), not the page size, so callers can compute page count.

        Sorting/pagination happen BEFORE the per-tenant hierarchical build (tier grouping,
        quota/percentage calcs, tier_first_seen, tenant-name resolution) — that build only
        runs for the tenants on the requested page, not the full matching tenant list.
        Sorting is by real spend (get_tenant_budgets, via _resolve_spent), which — unlike
        the old cost_accum-derived pre-aggregate this replaced — requires an auth_db
        lookup for the FULL matching tenant_ids, not just the page: real spend has no
        cheap per-usage-row proxy any more (see get_tenant_tier_usage_breakdown's
        docstring), so this auth_db round trip can no longer be deferred to the
        page-only budget lookup below. A worse cost for a real number, not a free one.
        """
        assignments = await self._repo.get_tenants_with_usage_tier(
            billing_month, tier_id, task_type_ids=task_type_ids
        )
        total = len(assignments)
        if not assignments:
            return TenantHierarchicalListResponse(data=[], total=0)

        tenant_ids = [row.tenant_id for row in assignments]
        # spend/budget/tierBreakdown are ALWAYS all-time — billing_month never narrows
        # them, even when explicitly given, since budget is a lifetime pool, not a
        # monthly figure (see _build_hierarchical_item's quota_usage_rows docstring).
        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
            None, tenant_ids, task_type_ids=task_type_ids
        )
        # Quota resets monthly, unlike spend, so it's scoped to billing_month when the
        # caller gives one, else the current calendar month — never all-time.
        quota_usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
            billing_month or current_billing_month(), tenant_ids, task_type_ids=task_type_ids
        )
        # Fetched for the FULL tenant_ids (not just the page) — sorting below needs
        # real spend for every matching tenant, not only the ones that end up on this
        # page (see this method's own docstring for why that's now unavoidable).
        budgets = await self._repo.get_tenant_budgets(billing_month, tenant_ids, auth_db)

        usage_by_tenant: dict[str, list] = {}
        for row in usage_rows:
            usage_by_tenant.setdefault(row.tenant_id, []).append(row)

        quota_usage_by_tenant: dict[str, list] = {}
        for row in quota_usage_rows:
            quota_usage_by_tenant.setdefault(row.tenant_id, []).append(row)

        # tenant_id as a secondary key breaks spend ties deterministically — without it,
        # tenants tied on spend (e.g. many at 0) could sort differently between two
        # sequential paginated calls, duplicating a tenant across pages or dropping one
        # entirely, even with the repository's own ORDER BY as a first line of defense.
        assignments.sort(
            key=lambda a: (_resolve_spent(a.tenant_id, budgets), a.tenant_id),
            reverse=(sort_order != "asc"),
        )
        page_assignments = assignments[offset : offset + limit]

        page_tenant_ids = [a.tenant_id for a in page_assignments]

        # tier_first_seen/tier_names are self._db-only; org_map is auth_db-only (a
        # second, page-scoped auth_db round trip alongside the full-scope budgets
        # fetch above — an AsyncSession supports sequential awaits, never concurrent
        # ones, so this can't share a coroutine with the budgets fetch, but it CAN run
        # concurrently with the self._db group since they're different sessions).
        async def _fetch_self_db_data():
            tier_first_seen = await self._repo.get_tier_first_seen(page_tenant_ids)
            tier_names = await self._repo.get_tier_names()
            return tier_first_seen, tier_names

        (tier_first_seen, tier_names), org_map = await asyncio.gather(
            _fetch_self_db_data(),
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
                quota_usage_by_tenant.get(assignment.tenant_id, []),
                model_task_type_id,
                order_by_tenant.get(assignment.tenant_id),
                tier_names,
            )
            for assignment in merged_page
        ]

        return TenantHierarchicalListResponse(data=items, total=total)

    async def get_tenant_detail(
        self,
        tenant_id: str,
        billing_month: str | None,
        auth_db: Optional[AsyncSession],
        task_type_ids: list[int] | None = None,
    ) -> TenantUsageDetailResponse:
        """Same hierarchical shape as get_tenant_list, scoped to a single tenant, except
        each tierBreakdown taskType entry omits spend/percentage (see
        _to_tenant_usage_detail) — /usage-tenants (the list endpoint) is the only one
        that still shows a per-task-type spend/percentage breakdown.
        spend/budget/tierBreakdown are ALWAYS all-time, whether billing_month is given
        or omitted — see get_tenant_list's docstring for the full spend-vs-quota split.
        Only the `usage` block's quota fields are scoped by billing_month: that month
        when given, else the current calendar month (see _build_hierarchical_item's
        quota_usage_rows docstring). The tenant's `tier` reflects whichever tier they
        were most recently active under in the same scope as get_tenants_with_usage_tier
        below, not from a separate assignment table. `budget` is a separate lookup via
        get_tenant_budgets, reconstructed from tenants.allocated_budget minus
        budget_usage spend — always the tenant's CURRENT balance (budget_usage has no
        per-billing-month dimension; see get_tenant_budgets' own docstring), and
        tierBreakdown covers every tier the tenant has ever had usage under, oldest first.
        `budget.budgetEffectiveFrom`/`budgetEffectiveTo` (only on this endpoint, not
        get_tenant_list) are tenants.budget_effective_from/to as-is — set once at
        tenant creation, untouched by budget top-up/top-down, null if never configured
        (see get_tenant_budgets' own docstring and TenantBudgetDetail).

        Unlike get_tenant_list, a tenant with zero ppu_quota_usage rows this
        billing_month is NOT omitted here — it falls into the zero-value branch
        below, so single-tenant lookups keep returning something for a valid
        tenant with no usage yet this period. `tier`/`tierId` in that branch
        still reflect the tenant's actual current tier (tenants.tier_id, via
        get_tenant_budgets) — falling back to "Unassigned" only when that
        tenant has no budget row at all (see get_tenant_budgets).
        """
        assignments = await self._repo.get_tenants_with_usage_tier(
            billing_month, tenant_id=tenant_id, task_type_ids=task_type_ids
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
            budgets = await self._repo.get_tenant_budgets(billing_month, [tenant_id], auth_db)
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
            # spend is REAL, tenant-total, and ALWAYS all-time (see get_tenant_list's
            # docstring) — a tenant with zero ppu_quota_usage rows for THIS billing_month
            # can still have real lifetime spend from other months (budget_usage has no
            # per-month dimension), so this must not collapse to 0 just because this
            # branch has no usage rows to build a hierarchical item from either.
            spent = round(_resolve_spent(tenant_id, budgets), 2)
            percentage_used = round(spent / budget_limit * 100, 1) if budget_limit > 0 else Decimal("0")

            return TenantUsageDetailResponse(
                tenantId=tenant_id,
                tenantName=org_map.get(tenant_id, tenant_id),
                tier=tier_name,
                tierId=tier_id,
                currency=_CURRENCY,
                spend=spent,
                budget=TenantBudgetDetail(
                    limit=budget_limit,
                    spent=spent,
                    remaining=available_balance,
                    percentageUsed=percentage_used,
                    budgetEffectiveFrom=budget_row.budget_effective_from if budget_row else None,
                    budgetEffectiveTo=budget_row.budget_effective_to if budget_row else None,
                ),
                usage=TenantUsageCount(taskTypeCount=0),
                tierBreakdown=[],
            )

        async def _fetch_self_db_data():
            # spend/budget/tierBreakdown are ALWAYS all-time — billing_month never
            # narrows them, even when explicitly given (budget is a lifetime pool).
            usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
                None, [tenant_id], task_type_ids=task_type_ids
            )
            # Quota resets monthly, unlike spend, so it's scoped to billing_month when
            # given, else the current calendar month — never all-time.
            quota_usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
                billing_month or current_billing_month(), [tenant_id], task_type_ids=task_type_ids
            )
            tier_first_seen = await self._repo.get_tier_first_seen([tenant_id])
            tier_names = await self._repo.get_tier_names()
            return usage_rows, quota_usage_rows, tier_first_seen, tier_names

        # get_tenant_budgets now also reads auth_db (AI4IDS-2923 rework) — see
        # get_tenant_list's identical restructuring for why it can no longer share a
        # concurrent group with a self._db-only fetch. Grouped with
        # _resolve_tenant_names instead: both auth_db calls run sequentially with
        # each other, while this whole group still runs concurrently against the
        # self._db group above.
        async def _fetch_auth_db_data():
            org_map = await _resolve_tenant_names([tenant_id], auth_db)
            budgets = await self._repo.get_tenant_budgets(billing_month, [tenant_id], auth_db)
            return org_map, budgets

        (usage_rows, quota_usage_rows, tier_first_seen, tier_names), (org_map, budgets) = await asyncio.gather(
            _fetch_self_db_data(),
            _fetch_auth_db_data(),
        )
        tier_order = {str(row.tier_id): row.first_seen for row in tier_first_seen}
        assignment = _merge_tier_and_budget(assignments, budgets, tier_names)[0]

        item = _build_hierarchical_item(
            assignment,
            org_map.get(tenant_id, tenant_id),
            usage_rows,
            quota_usage_rows,
            None,
            tier_order,
            tier_names,
        )
        return _to_tenant_usage_detail(
            item, assignment.budget_effective_from, assignment.budget_effective_to
        )
