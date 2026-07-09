"""PPU usage repository — reads usage and pricing data."""
from sqlalchemy import func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_management.service import Service
from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier, PPUTierQuota


class PPUUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_usage_with_pricing(self, billing_month: str):
        """Aggregates units_used and cost_accum per inference_name for the billing month."""
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                func.sum(PPUQuotaUsage.cost_accum).label("total_cost"),
            )
            .where(PPUQuotaUsage.billing_month == billing_month)
            .group_by(PPUQuotaUsage.inference_name)
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

        # quota_sq and unit_size_col are only meaningful when filtering by a single
        # inference type — mixing quotas across types (e.g. ASR minutes + LLM tokens)
        # produces a dimensionally incoherent sum that cannot be displayed.
        if model_task_type:
            quota_sq = (
                select(
                    PPUTierQuota.tier_id,
                    func.sum(PPUTierQuota.monthly_quota).label("total_quota"),
                )
                .where(PPUTierQuota.inference_name == model_task_type)
                .group_by(PPUTierQuota.tier_id)
                .subquery()
            )
            quota_col = quota_sq.c.total_quota.label("total_quota")
        else:
            quota_sq = None
            quota_col = null().label("total_quota")

        if model_task_type:
            unit_size_col = (
                select(Service.unit_size)
                .where(
                    Service.task_type == model_task_type.lower(),
                    Service.deleted_at.is_(None),
                )
                .order_by(Service.created_at.desc())
                .limit(1)
                .scalar_subquery()
                .label("unit_size")
            )
        else:
            unit_size_col = null().label("unit_size")

        stmt = (
            select(
                PPUTenantTierAssignment.tenant_id,
                PPUTier.name.label("tier_name"),
                PPUTenantTierAssignment.budget_limit,
                PPUTenantTierAssignment.available_balance,
                func.coalesce(usage_sq.c.total_units, 0).label("total_units"),
                quota_col,
                unit_size_col,
            )
            .join(PPUTier, PPUTier.id == PPUTenantTierAssignment.tier_id)
            .outerjoin(usage_sq, usage_sq.c.tenant_id == PPUTenantTierAssignment.tenant_id)
            .where(
                PPUTenantTierAssignment.effective_from <= func.now(),
                PPUTenantTierAssignment.effective_to > func.now(),
            )
        )
        if quota_sq is not None:
            stmt = stmt.outerjoin(quota_sq, quota_sq.c.tier_id == PPUTenantTierAssignment.tier_id)
        if tier:
            stmt = stmt.where(PPUTier.name == tier)

        result = await self._db.execute(stmt)
        return result.all()

    async def get_tenant_assignment(self, tenant_id: str):
        """Budget, balance, and tier name for a single tenant."""
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
                quota_sq.c.total_quota.label("total_quota"),
            )
            .join(PPUTier, PPUTier.id == PPUTenantTierAssignment.tier_id)
            .outerjoin(quota_sq, quota_sq.c.tier_id == PPUTenantTierAssignment.tier_id)
            .where(
                PPUTenantTierAssignment.tenant_id == tenant_id,
                PPUTenantTierAssignment.effective_from <= func.now(),
                PPUTenantTierAssignment.effective_to > func.now(),
            )
            .order_by(PPUTenantTierAssignment.effective_from.desc())
        )
        result = await self._db.execute(stmt)
        return result.first()

    async def get_tenant_period_breakdown(self, tenant_id: str, billing_month: str):
        """Per-inference-name usage and accumulated cost for a single tenant and billing month."""
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                func.sum(PPUQuotaUsage.cost_accum).label("total_cost"),
                func.max(PPUQuotaUsage.monthly_quota_snap).label("monthly_quota_snap"),
            )
            .where(
                PPUQuotaUsage.tenant_id == tenant_id,
                PPUQuotaUsage.billing_month == billing_month,
            )
            .group_by(PPUQuotaUsage.inference_name)
        )
        result = await self._db.execute(stmt)
        return result.all()
