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
    TenantUsageBreakdown,
    TenantUsageDetailResponse,
    TenantUsageItem,
    TenantUsageListResponse,
    UsageSummaryResponse,
)

_UNIT_LABELS: dict[str, str] = get_inference_unit_map()
_CURRENCY = "INR"


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

    async def get_summary(self, billing_month: str) -> UsageSummaryResponse:
        rows = await self._repo.get_usage_with_pricing(billing_month)

        items: list[dict] = []
        for row in rows:
            units = float(row.total_units or 0)
            unit_size = int(row.unit_size) if row.unit_size else 1

            if row.unit_rate:
                spend = round(float(units) * float(row.unit_rate), 2)
            elif row.cost_per_unit:
                spend = round((float(units) / unit_size) * float(row.cost_per_unit), 2)
            else:
                spend = 0.0

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

        return UsageSummaryResponse(
            billingPeriod=billing_month,
            totalSpend=round(total_spend, 2),
            currency=_CURRENCY,
            spendByModelTaskType=spend_items,
        )

    async def get_tenant_list(
        self,
        billing_month: str,
        tier: str | None,
        model_task_type: str | None,
        auth_db: Optional[AsyncSession],
    ) -> TenantUsageListResponse:
        rows = await self._repo.get_tenant_usages(billing_month, tier, model_task_type)
        org_map = await _resolve_tenant_names([row.tenant_id for row in rows], auth_db)
        unit_label = _UNIT_LABELS.get(model_task_type, "Units") if model_task_type else "Units"

        items = []
        for row in rows:
            budget_limit = float(row.budget_limit)
            remaining_budget = float(row.available_balance)
            total_units = float(row.total_units or 0)
            raw_quota = row.total_quota  # None means unlimited (no quota rows for this tier)
            quota_display = float(raw_quota) if raw_quota is not None else None

            items.append(TenantUsageItem(
                tenantId=row.tenant_id,
                tenantName=org_map.get(row.tenant_id, row.tenant_id),
                tier=row.tier_name,
                budgetLimit=round(budget_limit, 2),
                spendToDate=round(budget_limit - remaining_budget, 2),
                remainingBudget=round(remaining_budget, 2),
                quotaLimit=quota_display,
                quotaUnit=unit_label,
                consumptionToDate=total_units,
                remainingQuota=max(0, quota_display - total_units) if quota_display is not None else None,
                currency=_CURRENCY,
            ))

        return TenantUsageListResponse(data=items, total=len(items))

    async def get_tenant_detail(
        self,
        tenant_id: str,
        billing_month: str,
        auth_db: Optional[AsyncSession],
    ) -> TenantUsageDetailResponse:
        assignment = await self._repo.get_tenant_assignment(tenant_id)
        if not assignment:
            raise EntityNotFoundError(f"Tenant {tenant_id}")

        breakdown_rows = await self._repo.get_tenant_period_breakdown(tenant_id, billing_month)
        org_map = await _resolve_tenant_names([tenant_id], auth_db)

        breakdown: list[TenantUsageBreakdown] = []
        total_consumption = 0.0
        inference_types: set[str] = set()
        type_unit_sizes: dict[str, int] = {}  # kept for cost_per_unit billing calc

        raw: list[dict] = []
        for row in breakdown_rows:
            units = float(row.total_units or 0)
            unit_size = int(row.unit_size) if row.unit_size else 1
            total_consumption += units
            inference_types.add(row.inference_name)
            type_unit_sizes[row.inference_name] = unit_size

            if row.unit_rate:
                spend = round(float(units) * float(row.unit_rate), 2)
            elif row.cost_per_unit:
                spend = round((float(units) / unit_size) * float(row.cost_per_unit), 2)
            else:
                spend = 0.0

            snap = row.monthly_quota_snap
            if snap is not None:
                row_quota_limit = float(snap)
                row_remaining = max(0, row_quota_limit - units)
            else:
                row_quota_limit = None
                row_remaining = None

            raw.append(dict(
                modelTaskType=row.inference_name,
                consumptionToDate=units,
                unit=_UNIT_LABELS.get(row.inference_name, row.inference_name),
                spend=spend,
                quotaLimit=row_quota_limit,
                remainingQuota=row_remaining,
            ))

        total_spend = sum(r["spend"] for r in raw)
        breakdown = [
            TenantUsageBreakdown(
                **r,
                percentage=round(r["spend"] / total_spend * 100, 1) if total_spend > 0 else 0.0,
            )
            for r in raw
        ]

        # Use the specific unit label only when all usage is from one inference type;
        # fall back to "Units" when the tenant uses multiple service types.
        if len(inference_types) == 1:
            quota_unit = _UNIT_LABELS.get(next(iter(inference_types)), "Units")
        else:
            quota_unit = "Units"

        budget_limit = float(assignment.budget_limit)
        remaining_budget = float(assignment.available_balance)
        if len(inference_types) == 1:
            # Use the per-type quota snapshot from the breakdown row.
            # assignment.total_quota is SUM(monthly_quota) across ALL inference types
            # in the tier, which is wrong when the tier has quotas for multiple types
            # (e.g. LLM 1000 + ASR 500 → shows 1500 instead of 1000 for an LLM-only tenant).
            quota_display = raw[0].get("quotaLimit")
        else:
            quota_display = None

        multi_type = len(inference_types) > 1
        return TenantUsageDetailResponse(
            tenantId=tenant_id,
            tenantName=org_map.get(tenant_id, tenant_id),
            tier=assignment.tier_name,
            budgetLimit=round(budget_limit, 2),
            spendToDate=round(budget_limit - remaining_budget, 2),
            remainingBudget=round(remaining_budget, 2),
            quotaLimit=None if multi_type else quota_display,
            quotaUnit=quota_unit,
            consumptionToDate=None if multi_type else total_consumption,
            remainingQuota=None if multi_type else (
                max(0, quota_display - total_consumption) if quota_display is not None else None
            ),
            currency=_CURRENCY,
            breakdown=breakdown,
        )
