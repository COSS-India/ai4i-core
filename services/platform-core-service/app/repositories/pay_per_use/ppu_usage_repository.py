"""PPU usage repository — reads usage and pricing data."""
from sqlalchemy import func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_management.service import Service
from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier, PPUTierQuota


def _pricing_subquery():
    """
    One pricing row per billing_unit_type, choosing the most recently created
    non-deleted Service row.  Prevents double-counting when multiple Service
    rows share the same billing_unit_type (e.g. several LLM services all
    billed as 'llm').
    """
    inner = (
        select(
            Service.billing_unit_type,
            Service.cost_per_unit,
            Service.unit_size,
            Service.unit_rate,
            func.row_number()
            .over(
                partition_by=Service.billing_unit_type,
                order_by=Service.created_at.desc(),
            )
            .label("rn"),
        )
        .where(Service.deleted_at.is_(None))
        .subquery()
    )
    return (
        select(
            inner.c.billing_unit_type,
            inner.c.cost_per_unit,
            inner.c.unit_size,
            inner.c.unit_rate,
        )
        .where(inner.c.rn == 1)
        .subquery()
    )


class PPUUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_usage_with_pricing(self, billing_month: str):
        """
        Aggregates units_used per inference_name for the billing month,
        left-joined with mm_services pricing via billing_unit_type.
        """
        pricing_sq = _pricing_subquery()
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                pricing_sq.c.cost_per_unit,
                pricing_sq.c.unit_size,
                pricing_sq.c.unit_rate,
            )
            .outerjoin(
                pricing_sq,
                pricing_sq.c.billing_unit_type == PPUQuotaUsage.inference_name,
            )
            .where(PPUQuotaUsage.billing_month == billing_month)
            .group_by(
                PPUQuotaUsage.inference_name,
                pricing_sq.c.cost_per_unit,
                pricing_sq.c.unit_size,
                pricing_sq.c.unit_rate,
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

        # Fetch the correct unit_size for the filtered inference type so the
        # service layer can apply the right divisor (e.g. 60 for ASR minutes,
        # not the default 1M).  NULL when no type filter — units are mixed.
        if model_task_type:
            unit_size_col = (
                select(Service.unit_size)
                .where(
                    Service.billing_unit_type == model_task_type,
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
                func.coalesce(quota_sq.c.total_quota, 0).label("total_quota"),
                unit_size_col,
            )
            .join(PPUTier, PPUTier.id == PPUTenantTierAssignment.tier_id)
            .outerjoin(usage_sq, usage_sq.c.tenant_id == PPUTenantTierAssignment.tenant_id)
            .outerjoin(quota_sq, quota_sq.c.tier_id == PPUTenantTierAssignment.tier_id)
            .where(
                PPUTenantTierAssignment.effective_from <= func.now(),
                PPUTenantTierAssignment.effective_to > func.now(),
            )
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
        """Per-inference-name usage with pricing for a single tenant and billing month."""
        pricing_sq = _pricing_subquery()
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                pricing_sq.c.unit_size,
                pricing_sq.c.unit_rate,
                pricing_sq.c.cost_per_unit,
            )
            .outerjoin(
                pricing_sq,
                pricing_sq.c.billing_unit_type == PPUQuotaUsage.inference_name,
            )
            .where(
                PPUQuotaUsage.tenant_id == tenant_id,
                PPUQuotaUsage.billing_month == billing_month,
            )
            .group_by(
                PPUQuotaUsage.inference_name,
                pricing_sq.c.unit_size,
                pricing_sq.c.unit_rate,
                pricing_sq.c.cost_per_unit,
            )
        )
        result = await self._db.execute(stmt)
        return result.all()
