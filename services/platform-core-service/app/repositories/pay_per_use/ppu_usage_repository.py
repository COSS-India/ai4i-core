"""PPU usage repository — reads usage and pricing data."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_management.service import Service
from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier, PPUTierQuota


class PPUUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_usage_with_pricing(self, billing_month: str):
        """
        Aggregates units_used per inference_name for the billing month,
        left-joined with mm_services pricing via billing_unit_type.
        """
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                Service.cost_per_unit,
                Service.unit_size,
                Service.unit_rate,
            )
            .outerjoin(
                Service,
                (Service.billing_unit_type == PPUQuotaUsage.inference_name)
                & Service.deleted_at.is_(None),
            )
            .where(PPUQuotaUsage.billing_month == billing_month)
            .group_by(
                PPUQuotaUsage.inference_name,
                Service.cost_per_unit,
                Service.unit_size,
                Service.unit_rate,
            )
        )
        result = await self._db.execute(stmt)
        return result.all()

    async def get_tenant_usages(
        self, billing_month: str, tier: str | None, model_task_type: str | None
    ):
        """One row per tenant with aggregated period consumption and tier quota."""
        usage_sq = select(
            PPUQuotaUsage.tenant_id,
            func.sum(PPUQuotaUsage.units_used).label("total_units"),
        ).where(PPUQuotaUsage.billing_month == billing_month)
        if model_task_type:
            usage_sq = usage_sq.where(PPUQuotaUsage.inference_name == model_task_type)
        usage_sq = usage_sq.group_by(PPUQuotaUsage.tenant_id).subquery()

        quota_sq = select(
            PPUTierQuota.tier_id,
            func.sum(PPUTierQuota.monthly_quota).label("total_quota"),
        )
        if model_task_type:
            quota_sq = quota_sq.where(PPUTierQuota.inference_name == model_task_type)
        quota_sq = quota_sq.group_by(PPUTierQuota.tier_id).subquery()

        stmt = (
            select(
                PPUTenantTierAssignment.tenant_id,
                PPUTier.name.label("tier_name"),
                PPUTenantTierAssignment.budget_limit,
                PPUTenantTierAssignment.available_balance,
                func.coalesce(usage_sq.c.total_units, 0).label("total_units"),
                func.coalesce(quota_sq.c.total_quota, 0).label("total_quota"),
            )
            .join(PPUTier, PPUTier.id == PPUTenantTierAssignment.tier_id)
            .outerjoin(usage_sq, usage_sq.c.tenant_id == PPUTenantTierAssignment.tenant_id)
            .outerjoin(quota_sq, quota_sq.c.tier_id == PPUTenantTierAssignment.tier_id)
        )
        if tier:
            stmt = stmt.where(PPUTier.name == tier)

        result = await self._db.execute(stmt)
        return result.all()

    async def get_tenant_assignment(self, tenant_id: str):
        """Budget, balance, tier name, and total monthly quota for a single tenant."""
        quota_sq = (
            select(
                PPUTierQuota.tier_id,
                func.sum(PPUTierQuota.monthly_quota).label("total_quota"),
            )
            .group_by(PPUTierQuota.tier_id)
            .subquery()
        )
        stmt = (
            select(
                PPUTenantTierAssignment.budget_limit,
                PPUTenantTierAssignment.available_balance,
                PPUTier.name.label("tier_name"),
                func.coalesce(quota_sq.c.total_quota, 0).label("total_quota"),
            )
            .join(PPUTier, PPUTier.id == PPUTenantTierAssignment.tier_id)
            .outerjoin(quota_sq, quota_sq.c.tier_id == PPUTenantTierAssignment.tier_id)
            .where(PPUTenantTierAssignment.tenant_id == tenant_id)
        )
        result = await self._db.execute(stmt)
        return result.first()

    async def get_tenant_period_breakdown(self, tenant_id: str, billing_month: str):
        """Per-inference-name usage with pricing for a single tenant and billing month."""
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                Service.unit_size,
                Service.unit_rate,
                Service.cost_per_unit,
            )
            .outerjoin(
                Service,
                (Service.billing_unit_type == PPUQuotaUsage.inference_name)
                & Service.deleted_at.is_(None),
            )
            .where(
                PPUQuotaUsage.tenant_id == tenant_id,
                PPUQuotaUsage.billing_month == billing_month,
            )
            .group_by(
                PPUQuotaUsage.inference_name,
                Service.unit_size,
                Service.unit_rate,
                Service.cost_per_unit,
            )
        )
        result = await self._db.execute(stmt)
        return result.all()
