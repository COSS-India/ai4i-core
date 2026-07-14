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


def _count_budget_exceeded(tenant_rows) -> int:
    return sum(
        1 for row in tenant_rows
        if float(row.total_cost or 0) >= float(row.budget_limit)
    )


def _group_usage_by_tier(usage_rows) -> dict[str, dict]:
    """Groups flat (tier_id, inference_name) usage rows into {tier_key: {tierName, rows}}."""
    groups: dict[str, dict] = {}
    for row in usage_rows:
        tier_key = str(row.tier_id) if row.tier_id is not None else "unassigned"
        bucket = groups.setdefault(tier_key, {"tierName": row.tier_name or "Unassigned", "rows": []})
        bucket["rows"].append(row)
    return groups


def _build_hierarchical_item(assignment, tenant_name: str, usage_rows) -> TenantHierarchicalItem:
    """Builds one tenant's hierarchical usage item from their end-of-period tier assignment
    plus their flat per-(tier, inference_name) usage rows for the billing month.
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
        usage=TenantUsageCount(taskTypeCount=len(distinct_task_types)),
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

    async def get_summary(
        self,
        billing_month: str,
        tier_id: str | None = None,
        model_task_type: str | None = None,
    ) -> UsageSummaryResponse:
        rows = await self._repo.get_usage_with_pricing(billing_month, tier_id, model_task_type)

        items: list[dict] = []
        for row in rows:
            units = float(row.total_units or 0)
            spend = round(float(row.total_cost or 0), 2)

            items.append({
                "modelTaskType": row.inference_name,
                "unit": _UNIT_LABELS.get(row.inference_name, row.inference_name),
                "consumption": units,
                "spend": spend,
            })

        total_spend = sum(i["spend"] for i in items)
        spend_items = [
            SpendItem(
                **i,
                percentage=round(i["spend"] / total_spend * 100, 1) if total_spend > 0 else 0.0,
            )
            for i in items
        ]

        tenant_rows = await self._repo.get_tenant_usages(billing_month, tier_id, model_task_type)
        active_tenants = len(tenant_rows)
        budget_exceeded = _count_budget_exceeded(tenant_rows)

        prev_tenant_rows = await self._repo.get_tenant_usages(
            _prev_month(billing_month), tier_id, model_task_type
        )
        prev_budget_exceeded = _count_budget_exceeded(prev_tenant_rows)
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
