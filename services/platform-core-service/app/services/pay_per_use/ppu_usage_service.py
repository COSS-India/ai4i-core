"""PPU usage service — computes spend summary from DB rows."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai4i_core.ppu import get_inference_unit_map
from app.core.exceptions import EntityNotFoundError
from app.repositories.pay_per_use.ppu_usage_repository import PPUUsageRepository
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


def _prev_month(billing_month: str) -> str:
    year, month = (int(part) for part in billing_month.split("-"))
    month -= 1
    if month < 1:
        month, year = 12, year - 1
    return f"{year:04d}-{month:02d}"


def _group_usage_by_tier(usage_rows) -> dict[str, dict]:
    """Groups flat (tier_id, inference_name) usage rows into {tier_key: {tierName, rows}}."""
    groups: dict[str, dict] = {}
    for row in usage_rows:
        tier_key = str(row.tier_id) if row.tier_id is not None else "unassigned"
        bucket = groups.setdefault(tier_key, {"tierName": row.tier_name or "Unassigned", "rows": []})
        bucket["rows"].append(row)
    return groups


def _build_hierarchical_item(
    assignment,
    tenant_name: str,
    usage_rows,
    model_task_type: str | None = None,
    tier_order: dict[str, datetime] | None = None,
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
    tier_groups = _group_usage_by_tier(usage_rows)
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
    tenant_spend = 0.0

    for tier_key in ordered_tier_keys:
        bucket = tier_groups[tier_key]
        raw_task_types: list[dict] = []
        tier_spend = 0.0
        for row in bucket["rows"]:
            units = float(row.total_units or 0)
            spend = round(float(row.total_cost or 0), 2)
            quota = float(row.quota_snap) if row.quota_snap is not None else None
            remaining = round(max(0.0, quota - units), 2) if quota is not None else None
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
                    percentage=round(t["spend"] / tenant_spend * 100, 1) if tenant_spend > 0 else 0.0,
                )
                for t in tg["raw_task_types"]
            ],
        )
        for tg in tier_raw
    ]
    budget_limit = round(float(assignment.budget_limit), 2)
    remaining_budget = round(float(assignment.available_balance), 2)
    percentage_used = round(tenant_spend / budget_limit * 100, 1) if budget_limit > 0 else 0.0

    effective_task_type = model_task_type
    if effective_task_type is None and len(distinct_task_types) == 1:
        effective_task_type = next(iter(distinct_task_types))

    usage_count = TenantUsageCount(taskTypeCount=len(distinct_task_types))
    if effective_task_type:
        matching_rows = [r for r in usage_rows if r.inference_name == effective_task_type]
        total_consumed = sum(float(r.total_units or 0) for r in matching_rows)
        current_tier_row = next(
            (r for r in matching_rows if str(r.tier_id) == str(assignment.tier_id)), None
        )
        quota = (
            float(current_tier_row.quota_snap)
            if current_tier_row is not None and current_tier_row.quota_snap is not None
            else None
        )
        if quota is None:
            percentage = 0.0
        elif quota == 0:
            # A 0 quota is a deliberate "blocked for this cycle" tier setting (see
            # tier_service.py), not missing data — any usage against it is fully
            # exhausted, not 0% used.
            percentage = 100.0 if total_consumed > 0 else 0.0
        else:
            percentage = round(total_consumed / quota * 100, 1)

        usage_count = TenantUsageCount(
            taskTypeCount=len(distinct_task_types),
            unit=_UNIT_LABELS.get(effective_task_type, effective_task_type),
            quotaLimit=round(quota, 2) if quota is not None else None,
            consumed=round(total_consumed, 2),
            remaining=round(max(0.0, quota - total_consumed), 2) if quota is not None else None,
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


class PPUUsageService:
    def __init__(self, repo: PPUUsageRepository) -> None:
        self._repo = repo

    async def _tenant_assignments_and_usage(self, billing_month: str, tier_id: str | None):
        """Tenants belonging to tier_id as of the END of billing_month (not "as of now"),
        plus their usage rows for that month — the same tenant-selection rule used by
        get_tenant_list/get_tenant_detail, so a tier + billing_period filter combination
        gives consistent results across all three endpoints, including past periods where
        a tenant has since moved to a different tier.
        """
        assignments = await self._repo.get_tenant_tier_as_of_period_end(billing_month, tier_id)
        tenant_ids = [a.tenant_id for a in assignments]
        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(billing_month, tenant_ids)
        return assignments, usage_rows

    async def get_summary(
        self,
        billing_month: str,
        tier_id: str | None = None,
    ) -> UsageSummaryResponse:
        """model_task_type is intentionally NOT a filter here — the total-spend card and
        the spend-by-task-type chart always show every task type; only tier_id narrows
        which tenants are counted. (A task-type filter only affects the tenant table's
        per-row usage figure, on usage-tenants.)
        """
        assignments, usage_rows = await self._tenant_assignments_and_usage(billing_month, tier_id)

        by_task_type: dict[str, dict] = {}
        cost_by_tenant: dict[str, float] = {}
        for row in usage_rows:
            units = float(row.total_units or 0)
            cost = float(row.total_cost or 0)
            bucket = by_task_type.setdefault(
                row.inference_name,
                {"unit": _UNIT_LABELS.get(row.inference_name, row.inference_name), "units": 0.0, "cost": 0.0},
            )
            bucket["units"] += units
            bucket["cost"] += cost
            cost_by_tenant[row.tenant_id] = cost_by_tenant.get(row.tenant_id, 0.0) + cost

        total_spend = sum(b["cost"] for b in by_task_type.values())
        spend_items = [
            SpendItem(
                modelTaskType=name,
                unit=b["unit"],
                consumption=b["units"],
                spend=round(b["cost"], 2),
                percentage=round(b["cost"] / total_spend * 100, 1) if total_spend > 0 else 0.0,
            )
            for name, b in by_task_type.items()
        ]
        spend_items.sort(key=lambda i: i.spend, reverse=True)

        active_tenants = len(assignments)
        budget_exceeded = sum(
            1 for a in assignments
            if cost_by_tenant.get(a.tenant_id, 0.0) > float(a.budget_limit)
        )

        _, prev_usage_rows = await self._tenant_assignments_and_usage(
            _prev_month(billing_month), tier_id
        )
        prev_total_spend = sum(float(row.total_cost or 0) for row in prev_usage_rows)
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
    ) -> TenantHierarchicalListResponse:
        """Hierarchical tenant usage: tenant -> tier(s) held during billing_month -> task types.

        The tenant-level tier/budget reflect whichever tier assignment was in effect at the
        END of billing_month (which may differ from the tenant's tier "as of now" if they've
        since been reassigned). tierBreakdown covers every tier the tenant actually had usage
        under that month, oldest first — a mid-month tier change surfaces as two entries.

        model_task_type does NOT filter which tenants appear, nor narrow their spend/budget/
        tierBreakdown — those always reflect the full period. It only populates the flat
        `usage` quota-bar fields with that one task type's numbers (see _build_hierarchical_item).

        limit/offset paginate the sorted list; `total` in the response is the full matching
        tenant count (before slicing), not the page size, so callers can compute page count.
        """
        assignments = await self._repo.get_tenant_tier_as_of_period_end(billing_month, tier_id)
        if not assignments:
            return TenantHierarchicalListResponse(data=[], total=0)

        tenant_ids = [row.tenant_id for row in assignments]
        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(billing_month, tenant_ids)
        tier_first_seen = await self._repo.get_tier_first_seen(tenant_ids)
        org_map = await _resolve_tenant_names(tenant_ids, auth_db)

        usage_by_tenant: dict[str, list] = {}
        for row in usage_rows:
            usage_by_tenant.setdefault(row.tenant_id, []).append(row)

        order_by_tenant: dict[str, dict[str, datetime]] = {}
        for row in tier_first_seen:
            order_by_tenant.setdefault(row.tenant_id, {})[str(row.tier_id)] = row.first_seen

        items = [
            _build_hierarchical_item(
                assignment,
                org_map.get(assignment.tenant_id, assignment.tenant_id),
                usage_by_tenant.get(assignment.tenant_id, []),
                model_task_type,
                order_by_tenant.get(assignment.tenant_id),
            )
            for assignment in assignments
        ]

        items.sort(key=lambda item: item.spend, reverse=(sort_order != "asc"))
        total = len(items)
        return TenantHierarchicalListResponse(data=items[offset : offset + limit], total=total)

    async def get_tenant_detail(
        self,
        tenant_id: str,
        billing_month: str,
        auth_db: Optional[AsyncSession],
    ) -> TenantHierarchicalItem:
        """Same hierarchical shape as get_tenant_list, scoped to a single tenant — the
        tenant's tier/budget reflect whichever assignment was in effect at the END of
        billing_month, and tierBreakdown covers every tier they had usage under that
        month, oldest first.
        """
        assignments = await self._repo.get_tenant_tier_as_of_period_end(
            billing_month, tenant_id=tenant_id
        )
        if not assignments:
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        assignment = assignments[0]

        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(billing_month, [tenant_id])
        tier_first_seen = await self._repo.get_tier_first_seen([tenant_id])
        tier_order = {str(row.tier_id): row.first_seen for row in tier_first_seen}
        org_map = await _resolve_tenant_names([tenant_id], auth_db)

        return _build_hierarchical_item(
            assignment, org_map.get(tenant_id, tenant_id), usage_rows, None, tier_order
        )
