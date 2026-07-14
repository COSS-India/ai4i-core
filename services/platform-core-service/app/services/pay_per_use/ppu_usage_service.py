"""PPU usage service — computes spend summary from DB rows."""
from __future__ import annotations

import logging
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
) -> TenantHierarchicalItem:
    """Builds one tenant's hierarchical usage item from their end-of-period tier assignment
    plus their flat per-(tier, inference_name) usage rows for the billing month.

    When model_task_type is set, usage_rows are already pre-filtered to that single task
    type (by the repository query), so summing consumed/quota across rows here combines
    that same type's allotment across every tier the tenant held that month — e.g. tier1
    granted 500 tokens (100 used) then reassigned to tier2 granted 100 more (50 used) nets
    quotaLimit=600, consumed=150.
    """
    tier_groups = _group_usage_by_tier(usage_rows)

    tier_breakdown: list[TierUsageBreakdown] = []
    distinct_task_types: set[str] = set()
    tenant_spend = 0.0

    for tier_key, bucket in tier_groups.items():
        raw_task_types: list[dict] = []
        tier_spend = 0.0
        for row in bucket["rows"]:
            units = float(row.total_units or 0)
            spend = round(float(row.total_cost or 0), 2)
            quota = float(row.quota_snap) if row.quota_snap is not None else None
            remaining = round(quota - units, 2) if quota is not None else None
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

        task_types = [
            TaskTypeUsage(
                **t,
                percentage=round(t["spend"] / tier_spend * 100, 1) if tier_spend > 0 else 0.0,
            )
            for t in raw_task_types
        ]
        tier_breakdown.append(TierUsageBreakdown(
            tierId=tier_key,
            tierName=bucket["tierName"],
            spend=round(tier_spend, 2),
            taskTypes=task_types,
        ))
        tenant_spend += tier_spend

    tenant_spend = round(tenant_spend, 2)
    budget_limit = round(float(assignment.budget_limit), 2)
    remaining_budget = round(float(assignment.available_balance), 2)
    percentage_used = round(tenant_spend / budget_limit * 100, 1) if budget_limit > 0 else 0.0

    usage_count = TenantUsageCount(taskTypeCount=len(distinct_task_types))
    if model_task_type:
        total_consumed = sum(float(row.total_units or 0) for row in usage_rows)
        quota_values = [float(row.quota_snap) for row in usage_rows if row.quota_snap is not None]
        total_quota = sum(quota_values) if quota_values else None
        usage_count = TenantUsageCount(
            taskTypeCount=len(distinct_task_types),
            unit=_UNIT_LABELS.get(model_task_type, model_task_type),
            quotaLimit=round(total_quota, 2) if total_quota is not None else None,
            consumed=round(total_consumed, 2),
            remaining=round(total_quota - total_consumed, 2) if total_quota is not None else None,
            percentage=round(total_consumed / total_quota * 100, 1) if total_quota else 0.0,
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

    async def _tenants_and_spend_for_period(
        self, billing_month: str, tier_id: str | None, model_task_type: str | None
    ):
        """Tenants belonging to tier_id as of the END of billing_month (not "as of now"),
        plus their usage rows for that month — the same tenant-selection rule used by
        get_tenant_list/get_tenant_detail, so a tier + billing_period filter combination
        gives consistent results across all three endpoints, including past periods where
        a tenant has since moved to a different tier.
        """
        assignments = await self._repo.get_tenant_tier_as_of_period_end(billing_month, tier_id)
        tenant_ids = [a.tenant_id for a in assignments]
        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
            billing_month, tenant_ids, model_task_type
        )
        return assignments, usage_rows

    async def get_summary(
        self,
        billing_month: str,
        tier_id: str | None = None,
        model_task_type: str | None = None,
    ) -> UsageSummaryResponse:
        assignments, usage_rows = await self._tenants_and_spend_for_period(
            billing_month, tier_id, model_task_type
        )

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
            if cost_by_tenant.get(a.tenant_id, 0.0) >= float(a.budget_limit)
        )

        prev_assignments, prev_usage_rows = await self._tenants_and_spend_for_period(
            _prev_month(billing_month), tier_id, model_task_type
        )
        prev_cost_by_tenant: dict[str, float] = {}
        for row in prev_usage_rows:
            prev_cost_by_tenant[row.tenant_id] = prev_cost_by_tenant.get(row.tenant_id, 0.0) + float(row.total_cost or 0)
        prev_budget_exceeded = sum(
            1 for a in prev_assignments
            if prev_cost_by_tenant.get(a.tenant_id, 0.0) >= float(a.budget_limit)
        )
        budget_exceeded_change_percent = (
            round((budget_exceeded - prev_budget_exceeded) / prev_budget_exceeded * 100, 1)
            if prev_budget_exceeded > 0
            else None
        )

        return UsageSummaryResponse(
            billingPeriod=billing_month,
            totalSpend=round(total_spend, 2),
            currency=_CURRENCY,
            activeTenants=active_tenants,
            budgetExceededTenants=budget_exceeded,
            budgetExceededChangePercent=budget_exceeded_change_percent,
            spendByModelTaskType=spend_items,
        )

    async def get_tenant_list(
        self,
        billing_month: str,
        tier_id: str | None,
        model_task_type: str | None,
        auth_db: Optional[AsyncSession],
        sort_order: str = "desc",
    ) -> TenantHierarchicalListResponse:
        """Hierarchical tenant usage: tenant -> tier(s) held during billing_month -> task types.

        The tenant-level tier/budget reflect whichever tier assignment was in effect at the
        END of billing_month (which may differ from the tenant's tier "as of now" if they've
        since been reassigned). tierBreakdown covers every tier the tenant actually had usage
        under that month — a mid-month tier change surfaces as two entries.
        """
        assignments = await self._repo.get_tenant_tier_as_of_period_end(billing_month, tier_id)
        if not assignments:
            return TenantHierarchicalListResponse(data=[], total=0)

        tenant_ids = [row.tenant_id for row in assignments]
        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(
            billing_month, tenant_ids, model_task_type
        )
        org_map = await _resolve_tenant_names(tenant_ids, auth_db)

        usage_by_tenant: dict[str, list] = {}
        for row in usage_rows:
            usage_by_tenant.setdefault(row.tenant_id, []).append(row)

        items: list[TenantHierarchicalItem] = []
        for assignment in assignments:
            tenant_usage_rows = usage_by_tenant.get(assignment.tenant_id)
            if model_task_type and not tenant_usage_rows:
                continue  # no usage of the filtered task type this period — excluded entirely
            items.append(_build_hierarchical_item(
                assignment,
                org_map.get(assignment.tenant_id, assignment.tenant_id),
                tenant_usage_rows or [],
                model_task_type,
            ))

        items.sort(key=lambda item: item.spend, reverse=(sort_order != "asc"))
        return TenantHierarchicalListResponse(data=items, total=len(items))

    async def get_tenant_detail(
        self,
        tenant_id: str,
        billing_month: str,
        auth_db: Optional[AsyncSession],
    ) -> TenantHierarchicalItem:
        """Same hierarchical shape as get_tenant_list, scoped to a single tenant — the
        tenant's tier/budget reflect whichever assignment was in effect at the END of
        billing_month, and tierBreakdown covers every tier they had usage under that month.
        """
        assignments = await self._repo.get_tenant_tier_as_of_period_end(
            billing_month, tenant_id=tenant_id
        )
        if not assignments:
            raise EntityNotFoundError(f"Tenant {tenant_id}")
        assignment = assignments[0]

        usage_rows = await self._repo.get_tenant_tier_usage_breakdown(billing_month, [tenant_id])
        org_map = await _resolve_tenant_names([tenant_id], auth_db)

        return _build_hierarchical_item(
            assignment, org_map.get(tenant_id, tenant_id), usage_rows
        )
