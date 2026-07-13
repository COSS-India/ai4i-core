"""PPU usage repository — reads usage and accrued cost data."""
from sqlalchemy import case, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_management.service import Service
from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier, PPUTierQuota


class PPUUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_usage_with_pricing(
        self,
        billing_month: str,
        tier_id: str | None = None,
        model_task_type: str | None = None,
    ):
        """
        Aggregates units_used and cost_accum per inference_name for the billing month.
        cost_accum is accrued by the payperuse consumer at the price in effect when
        each request was made, so this reflects actual billed cost rather than a
        current-price projection.

        tier_id filters to tenants currently assigned to that tier; model_task_type
        filters to a single inference_name.
        """
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                func.sum(PPUQuotaUsage.cost_accum).label("total_cost"),
            )
            .where(PPUQuotaUsage.billing_month == billing_month)
        )
        if model_task_type:
            stmt = stmt.where(PPUQuotaUsage.inference_name == model_task_type)
        if tier_id:
            tier_tenant_sq = (
                select(PPUTenantTierAssignment.tenant_id)
                .where(
                    PPUTenantTierAssignment.tier_id == tier_id,
                    PPUTenantTierAssignment.effective_from <= func.now(),
                    PPUTenantTierAssignment.effective_to > func.now(),
                )
            )
            stmt = stmt.where(PPUQuotaUsage.tenant_id.in_(tier_tenant_sq))
        stmt = stmt.group_by(PPUQuotaUsage.inference_name)
        result = await self._db.execute(stmt)
        return result.all()

    async def get_tenant_usages(
        self, billing_month: str, tier_id: str | None, model_task_type: str | None
    ):
        """One row per tenant with aggregated period consumption and tier quota."""
        usage_sq = select(
            PPUQuotaUsage.tenant_id,
            func.sum(PPUQuotaUsage.units_used).label("total_units"),
            func.sum(PPUQuotaUsage.cost_accum).label("total_cost"),
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
                func.coalesce(usage_sq.c.total_cost, 0).label("total_cost"),
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
        if tier_id:
            stmt = stmt.where(PPUTenantTierAssignment.tier_id == tier_id)

        result = await self._db.execute(stmt)
        return result.all()

    async def get_tenant_assignment(self, tenant_id: str):
        """Budget, balance, and tier name for a single tenant.

        unit_size is intentionally omitted — callers derive it from breakdown rows
        (get_tenant_period_breakdown) which already carry the correct per-type unit_size
        via _pricing_subquery(). A single unit_size here would be arbitrary for
        multi-quota tiers and redundant for single-type tenants.
        """
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
        """Per-inference-name usage and accrued cost for a single tenant and billing month.

        units_used/cost_accum are summed across all tier rows in the month, since total
        consumption/spend must include usage recorded before a mid-month tier reassignment.
        monthly_quota_snap, however, must reflect only the tenant's CURRENT tier — a mid-month
        reassignment inserts a new (tenant_id, inference_name, billing_month, tier_id) row
        rather than updating the old one, so a plain MAX()/SUM() across rows would mix the old
        tier's quota in with the new one.
        """
        current_tier_sq = (
            select(PPUTenantTierAssignment.tier_id)
            .where(
                PPUTenantTierAssignment.tenant_id == tenant_id,
                PPUTenantTierAssignment.effective_from <= func.now(),
                PPUTenantTierAssignment.effective_to > func.now(),
            )
            .order_by(PPUTenantTierAssignment.effective_from.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                func.sum(PPUQuotaUsage.cost_accum).label("total_cost"),
                func.max(
                    case(
                        (PPUQuotaUsage.tier_id == current_tier_sq, PPUQuotaUsage.monthly_quota_snap),
                        else_=null(),
                    )
                ).label("monthly_quota_snap"),
            )
            .where(
                PPUQuotaUsage.tenant_id == tenant_id,
                PPUQuotaUsage.billing_month == billing_month,
            )
            .group_by(PPUQuotaUsage.inference_name)
        )
        result = await self._db.execute(stmt)
        return result.all()
