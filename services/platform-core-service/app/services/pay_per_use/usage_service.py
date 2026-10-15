"""Usage service — the Usage Dashboard's Budget tab.

/usage-summary (the Key metrics strip) returns two blocks with their own time
basis: budget (all-time, budget_usage) and quota (a billing month,
quota_usage). /usage-tenants and /usage-tenant
report the selected period: spend and usage from usage_events or
daily_usage (see period_usage.period_source), next to the all-time budget balance
(budget_usage) and the current billing month's quota (quota_usage).
"""
from __future__ import annotations

import logging
import uuid
from datetime import timezone
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError
from app.repositories.pay_per_use.usage_repository import UsageRepository
from app.utils.billing_month import current_billing_month
from app.schemas.pay_per_use.usage import (
    CostShare,
    MonthlyQuota,
    PeriodUsage,
    QuotaUsageItem,
    SummaryBudget,
    SummaryQuota,
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
from app.utils.rounding import round_parts, round_shares
from app.utils.usage_period import IST, UsagePeriod

# Unit labels come off the catalogue join now (see UsageRepository
# .get_tenant_tier_usage_breakdown, which selects InferenceType.unit). The
# import-time YAML snapshot this replaced could not see a type added after
# the process started, which is precisely what the catalogue exists to fix.
_CURRENCY = "INR"
# The catalogue name of the one task type billed by token category.
_LLM_TASK_TYPE = "llm"
_COST_ENTRIES = (
    ("input", "Input tokens"),
    ("cached_input", "Cached input tokens"),
    ("output", "Output tokens"),
)


def _tier_key(tier_id) -> str:
    """Canonical string key for a tier_id, including the null ("unassigned"/deleted
    tier) case — the single source of truth for matching a usage row's tier_id
    against another's (usage vs. quota rows, tier filters), so the two can never drift
    into comparing "None" against "unassigned"."""
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
    only for pre-catalogue rows, which echo their own name — the same fallback
    the bundled unit map gave an unrecognised type.
    """
    return getattr(row, "task_type_unit", None) or row.task_type


def _period_usage(rows, is_llm: bool) -> PeriodUsage:
    """A task type's units and cost in the period, summed over ``rows``
    (one per tier/type group from get_period_usage). For LLM, the cost split
    into uncached input, cached input and output — they sum to the totals,
    and cached input is omitted when it has no units."""
    def total(field: str) -> Decimal:
        return sum((_to_decimal(getattr(r, field)) for r in rows), Decimal("0"))

    units, cost = total("total_units"), total("cost")
    breakdown = None
    if is_llm:
        cached, output = total("cached_input_units"), total("output_units")
        parts = {
            "input": (units - cached - output, total("input_units_cost")),
            "cached_input": (cached, total("cached_input_units_cost")),
            "output": (output, total("output_units_cost")),
        }
        shown = [
            (key, label) for key, label in _COST_ENTRIES
            if not (key == "cached_input" and parts[key][0] == 0)
        ]
        # Rounded so the parts add up exactly: costs to the rounded total,
        # shares to 100.00 (the residual goes to the largest part).
        costs = round_parts([parts[key][1] for key, _ in shown], cost)
        shares = round_shares([parts[key][1] for key, _ in shown])
        breakdown = [
            CostShare(
                key=key, label=label, units=float(parts[key][0]),
                cost=float(costs[i]), costShare=float(shares[i]),
            )
            for i, (key, label) in enumerate(shown)
        ]
    return PeriodUsage(units=float(units), cost=float(round_parts([cost], cost)[0]), breakdown=breakdown)


def _monthly_quota(quota_row, billing_month: str) -> Optional[MonthlyQuota]:
    """The current billing month's quota from a quota_usage breakdown row,
    or None without one (or without a quota snapshot on it)."""
    if quota_row is None or quota_row.quota_snap is None:
        return None
    limit, used = _to_decimal(quota_row.quota_snap), _to_decimal(quota_row.total_units)
    if limit == 0:
        # A 0 quota is a deliberate "blocked for this cycle" tier setting (see
        # tier_service.py): any usage against it is fully exhausted.
        percentage = 100.0 if used > 0 else 0.0
    else:
        percentage = float(round(used / limit * 100, 2))
    return MonthlyQuota(
        billingMonth=billing_month, limit=float(limit), used=float(used),
        remaining=float(limit - used), percentageUsed=percentage,
    )


def _latest_tier(period_rows):
    """The tier of the most recent usage among ``period_rows`` (a tenant's).
    Ties on last activity go to a real tier over a deleted one (NULL), then
    to the higher tier id, so the pick is deterministic."""
    latest = max(
        period_rows,
        key=lambda r: (r.last_seen, r.tier_id is not None, str(r.tier_id or "")),
    )
    return latest.tier_id


def _in_ist(dt):
    """A DB timestamp in IST, so it serializes with +05:30 like every other
    Usage Dashboard timestamp. None stays None; a naive value is read as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def _period_spend(period_rows) -> Decimal:
    return sum((_to_decimal(r.cost) for r in period_rows), Decimal("0"))


def _build_period_item(
    tenant_id: str,
    tenant_name: str,
    period_rows,
    quota_rows,
    budgets_by_tenant: dict,
    tier_names: dict,
    billing_month: str,
) -> TenantHierarchicalItem:
    """One institution's Budget-tab item for the period.

    tierBreakdown has one entry per (tier, task type) with usage in the
    period or a quota this billing month, so the quota bar still shows on a
    day with no usage yet. Tiers are ordered by first activity in the
    period; tiers known only from this month's quota come last. Each task
    type pairs its period usage with the quota row of the same tier and
    type. tier/tierId is the tier of the most recent usage in the period, or
    the institution's current tier (tenants.tier_id) without any.
    """
    cells: dict[tuple[str, object], dict] = {}

    def cell(row) -> dict:
        key = (_tier_key(row.tier_id), _task_type_key(row))
        return cells.setdefault(key, {
            "tier_id": row.tier_id, "task_type": row.task_type, "unit": _row_unit(row),
            "rows": [], "quota": None,
        })

    for row in period_rows:
        cell(row)["rows"].append(row)
    for row in quota_rows:
        cell(row)["quota"] = row

    tiers: dict[str, dict] = {}
    for (tier_key, _), c in cells.items():
        first = min((r.first_seen for r in c["rows"]), default=None)
        tier = tiers.setdefault(tier_key, {"tier_id": c["tier_id"], "first_seen": None, "cells": []})
        tier["cells"].append(c)
        if first is not None and (tier["first_seen"] is None or first < tier["first_seen"]):
            tier["first_seen"] = first

    ordered = sorted(
        tiers.items(),
        key=lambda kv: (kv[1]["first_seen"] is None, kv[1]["first_seen"] or 0, kv[0]),
    )
    tier_breakdown = [
        TierUsageBreakdown(
            tierId=tier_key,
            tierName=_resolve_tier_name(tier["tier_id"], tier_names),
            taskTypes=[
                TaskTypeUsage(
                    taskType=c["task_type"],
                    unit=c["unit"],
                    quota=_monthly_quota(c["quota"], billing_month),
                    periodUsage=_period_usage(
                        c["rows"], (c["task_type"] or "").lower() == _LLM_TASK_TYPE,
                    ),
                )
                for c in sorted(tier["cells"], key=lambda c: c["task_type"] or "")
            ],
        )
        for tier_key, tier in ordered
    ]

    budget_row = budgets_by_tenant.get(tenant_id)
    if period_rows:
        current_tier = _latest_tier(period_rows)
    else:
        current_tier = budget_row.tier_id if budget_row is not None else None
    budget_limit, available_balance, _ = _resolve_budget(tenant_id, budgets_by_tenant)
    spent = round(_resolve_spent(tenant_id, budgets_by_tenant), 2)
    budget_limit = round(budget_limit, 2)
    return TenantHierarchicalItem(
        tenantId=tenant_id,
        tenantName=tenant_name,
        tier=_resolve_tier_name(current_tier, tier_names),
        tierId=_tier_key(current_tier),
        currency=_CURRENCY,
        periodSpend=round(_period_spend(period_rows), 2),
        budget=TenantBudget(
            limit=budget_limit,
            spent=spent,
            remaining=round(available_balance, 2),
            percentageUsed=round(spent / budget_limit * 100, 1) if budget_limit > 0 else Decimal("0"),
        ),
        usage=TenantUsageCount(taskTypeCount=len({_task_type_key(r) for r in period_rows})),
        tierBreakdown=tier_breakdown,
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
        """The Key metrics strip, as two independent blocks with their own time
        basis: ``budget`` is all-time (see _budget_summary) and ``quota`` is the
        billing month (see _quota_summary). billing_month scopes quota only.
        tier_id narrows both, each by its own tier (current tier vs. most recent
        tier in the quota rows; each block's tierFilter names it);
        task_type_ids narrows quota only, as spend has no per-task-type split.
        Without auth_db the budget block is all zeros."""
        return UsageSummaryResponse(
            currency=_CURRENCY,
            budget=await self._budget_summary(tier_id, auth_db),
            quota=await self._quota_summary(billing_month, tier_id, task_type_ids),
        )

    async def _budget_summary(self, tier_id: str | None, auth_db: Optional[AsyncSession]) -> SummaryBudget:
        """Budget across every institution with a budget on file — all-time,
        since budget_usage is a lifetime running total. Institutions come from
        tenants, not quota rows, so ones on untiered keys (spend, no quota rows)
        are counted; tier_id keeps those currently on that tier (tierFilter says
        so in the response, as the quota block picks by a different tier).

        exceededTenants counts institutions whose lifetime spend has reached
        their budget: institution spend >= institution budget, the same >=
        comparison billing applies per key — but per institution, so it isn't
        the number of institutions with blocked keys. A zero budget isn't
        counted: nothing was allocated to exhaust."""
        budgets = await self._repo.get_budgeted_tenant_budgets(auth_db, tier_id)
        allocated = spent = remaining = Decimal("0")
        exceeded = 0
        for tid in budgets:
            budget_limit, available_balance, has_budget = _resolve_budget(tid, budgets)
            if not has_budget:
                continue
            tenant_spent = _resolve_spent(tid, budgets)
            allocated += budget_limit
            spent += tenant_spent
            remaining += available_balance
            if budget_limit > 0 and tenant_spent >= budget_limit:
                exceeded += 1
        return SummaryBudget(
            institutions=len(budgets),
            allocated=round(allocated, 2),
            spent=round(spent, 2),
            remaining=round(remaining, 2),
            exceededTenants=exceeded,
            tierFilter="current_tier" if tier_id else None,
        )

    async def _quota_summary(
        self, billing_month: str | None, tier_id: str | None, task_type_ids: list[int] | None,
    ) -> SummaryQuota:
        """Quota usage per task type in billing_month (all months when None),
        across institutions with ppu_quota_usage rows in scope — tier_id keeps
        those whose most recent tier in scope is that tier."""
        assignments, usage_rows = await self._tenant_assignments_and_usage(
            billing_month, tier_id, task_type_ids
        )

        by_task_type: dict[str, dict] = {}
        for row in usage_rows:
            bucket = by_task_type.setdefault(
                _task_type_key(row),
                {"name": row.task_type, "unit": _row_unit(row), "units": Decimal("0")},
            )
            bucket["units"] += _to_decimal(row.total_units)

        # Quota allocated per task type, summed across tenants' CURRENT tier only (not
        # summed across every tier a tenant held that month): a quota grant resets
        # on reassignment, it isn't cumulative.
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

        # Keyed by catalogue id, but modelTaskType stays the name string.
        items = [
            QuotaUsageItem(
                modelTaskType=b["name"],
                unit=b["unit"],
                consumption=b["units"],
                allocated=round(allocated_by_task_type[key], 2) if key in allocated_by_task_type else None,
            )
            for key, b in by_task_type.items()
        ]
        items.sort(key=lambda i: i.consumption, reverse=True)
        return SummaryQuota(
            basis="billing_month" if billing_month else "all_time",
            billingMonth=billing_month,
            activeTenants=len(assignments),
            byTaskType=items,
            tierFilter="most_recent_quota_tier" if tier_id else None,
        )

    async def get_tenant_list(
        self,
        period: UsagePeriod,
        tier_id: str | None,
        model_task_type_id: int | None,
        auth_db: Optional[AsyncSession],
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
        task_type_ids: list[int] | None = None,
    ) -> TenantHierarchicalListResponse:
        """Institutions with usage in ``period`` (see period_usage.period_source),
        sorted by spend in the period (tenant id as the tie-break, so pages
        stay stable) and paginated; ``total`` is the count before limit/offset.

        tier_id keeps institutions whose most recent tier in the period is
        that tier; model_task_type_id keeps those that used that task type in
        the period. task_type_ids narrows every figure to those task types.
        period.dataFrom/partial say how much of the period the usage data
        covers, so an empty page can read as "no data" rather than "no usage"
        (see period_usage.usage_data_from).

        Only the page's institutions get the all-time balance, this month's
        quota, names and tier names. Queries run one after another: the
        budget lookup reads the core-DB session too, and an AsyncSession
        isn't safe for concurrent use.
        """
        rows = await self._repo.get_period_usage(period, task_type_ids=task_type_ids)
        by_tenant: dict[str, list] = {}
        for row in rows:
            by_tenant.setdefault(str(row.tenant_id), []).append(row)
        period_block = period.to_schema(
            await self._repo.get_usage_data_from(period), await self._repo.get_recorded_from(),
        )

        wanted_tier = str(uuid.UUID(tier_id)) if tier_id else None
        candidates = []
        for tid, tenant_rows in by_tenant.items():
            if model_task_type_id is not None and not any(
                r.inference_type_id == model_task_type_id for r in tenant_rows
            ):
                continue
            if wanted_tier is not None and _tier_key(_latest_tier(tenant_rows)) != wanted_tier:
                continue
            candidates.append((_period_spend(tenant_rows), int(tid), tid))

        candidates.sort(reverse=(sort_order != "asc"))
        page_ids = [tid for _, _, tid in candidates[offset : offset + limit]]
        if not page_ids:
            return TenantHierarchicalListResponse(
                period=period_block, data=[], total=len(candidates),
            )

        billing_month = current_billing_month()
        quota_rows = await self._repo.get_tenant_tier_usage_breakdown(
            billing_month, page_ids, task_type_ids=task_type_ids
        )
        tier_names = await self._repo.get_tier_names()
        budgets = await self._repo.get_tenant_budgets(page_ids, auth_db)
        org_map = await _resolve_tenant_names(page_ids, auth_db)

        quota_by_tenant: dict[str, list] = {}
        for row in quota_rows:
            quota_by_tenant.setdefault(str(row.tenant_id), []).append(row)

        items = [
            _build_period_item(
                tid, org_map.get(tid, tid), by_tenant[tid], quota_by_tenant.get(tid, []),
                budgets, tier_names, billing_month,
            )
            for tid in page_ids
        ]
        return TenantHierarchicalListResponse(
            period=period_block, data=items, total=len(candidates),
        )

    async def get_tenant_detail(
        self,
        tenant_id: str,
        period: UsagePeriod,
        auth_db: Optional[AsyncSession],
        task_type_ids: list[int] | None = None,
    ) -> TenantUsageDetailResponse:
        """One institution's Budget-tab details for ``period`` — the same item
        as get_tenant_list, plus the budget's effective window. Returned even
        with no usage in the period (periodSpend 0, task types from this
        month's quota with zero period usage), so the panel can show an empty
        state; an institution that doesn't exist is a 404 (checked only when
        it has no usage, and only with auth_db to check against).
        """
        period_rows = await self._repo.get_period_usage(
            period, tenant_ids=[tenant_id], task_type_ids=task_type_ids
        )
        org_map = await _resolve_tenant_names([tenant_id], auth_db)
        if not period_rows and auth_db is not None and tenant_id not in org_map:
            raise EntityNotFoundError(f"Tenant {tenant_id}")

        billing_month = current_billing_month()
        quota_rows = await self._repo.get_tenant_tier_usage_breakdown(
            billing_month, [tenant_id], task_type_ids=task_type_ids
        )
        tier_names = await self._repo.get_tier_names()
        budgets = await self._repo.get_tenant_budgets([tenant_id], auth_db)

        item = _build_period_item(
            tenant_id, org_map.get(tenant_id, tenant_id), period_rows, quota_rows,
            budgets, tier_names, billing_month,
        )
        budget_row = budgets.get(tenant_id)
        return TenantUsageDetailResponse(
            period=period.to_schema(
                await self._repo.get_usage_data_from(period), await self._repo.get_recorded_from(),
            ),
            tenantId=item.tenantId,
            tenantName=item.tenantName,
            tier=item.tier,
            tierId=item.tierId,
            currency=item.currency,
            periodSpend=item.periodSpend,
            budget=TenantBudgetDetail(
                **item.budget.model_dump(),
                budgetEffectiveFrom=_in_ist(budget_row.budget_effective_from) if budget_row else None,
                budgetEffectiveTo=_in_ist(budget_row.budget_effective_to) if budget_row else None,
            ),
            usage=item.usage,
            tierBreakdown=item.tierBreakdown,
        )
