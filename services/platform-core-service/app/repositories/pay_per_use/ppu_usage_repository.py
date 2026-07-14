"""PPU usage repository — reads usage and accrued cost data."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_management.service import Service
from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier, PPUTierQuota


def _end_of_month(billing_month: str) -> datetime:
    """Last instant (UTC) of the given YYYY-MM billing month."""
    year, month = (int(part) for part in billing_month.split("-"))
    if month == 12:
        next_month_start = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month_start = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return next_month_start - timedelta(microseconds=1)


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
        stmt = (
            stmt.group_by(PPUQuotaUsage.inference_name)
            .order_by(func.sum(PPUQuotaUsage.cost_accum).desc())
        )
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


    async def get_tenant_tier_as_of_period_end(
        self,
        billing_month: str,
        tier_id: str | None = None,
        tenant_id: str | None = None,
    ):
        """One row per tenant: whichever tier assignment was in effect at the end of
        billing_month (the assignment with the latest effective_from at or before that
        instant). This may differ from the tenant's assignment as of "now" when the
        tenant has since moved to a different tier.
        """
        end_instant = _end_of_month(billing_month)
        ranked = (
            select(
                PPUTenantTierAssignment.tenant_id,
                PPUTenantTierAssignment.tier_id,
                PPUTier.name.label("tier_name"),
                PPUTenantTierAssignment.budget_limit,
                PPUTenantTierAssignment.available_balance,
                func.row_number()
                .over(
                    partition_by=PPUTenantTierAssignment.tenant_id,
                    order_by=PPUTenantTierAssignment.effective_from.desc(),
                )
                .label("rn"),
            )
            .join(PPUTier, PPUTier.id == PPUTenantTierAssignment.tier_id)
            .where(PPUTenantTierAssignment.effective_from <= end_instant)
        )
        if tenant_id:
            ranked = ranked.where(PPUTenantTierAssignment.tenant_id == tenant_id)
        ranked = ranked.subquery()
        stmt = select(ranked).where(ranked.c.rn == 1)
        if tier_id:
            stmt = stmt.where(ranked.c.tier_id == tier_id)
        result = await self._db.execute(stmt)
        return result.all()

    async def get_tenant_tier_usage_breakdown(
        self,
        billing_month: str,
        tenant_ids: list[str],
        model_task_type: str | None = None,
    ):
        """Per (tenant, tier, inference_name) usage/cost for the billing month, across
        every tier the tenant held that month — not just their tier as of period end.
        """
        if not tenant_ids:
            return []
        stmt = (
            select(
                PPUQuotaUsage.tenant_id,
                PPUQuotaUsage.tier_id,
                PPUTier.name.label("tier_name"),
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                func.sum(PPUQuotaUsage.cost_accum).label("total_cost"),
                func.max(PPUQuotaUsage.monthly_quota_snap).label("quota_snap"),
            )
            .outerjoin(PPUTier, PPUTier.id == PPUQuotaUsage.tier_id)
            .where(
                PPUQuotaUsage.billing_month == billing_month,
                PPUQuotaUsage.tenant_id.in_(tenant_ids),
            )
        )
        if model_task_type:
            stmt = stmt.where(PPUQuotaUsage.inference_name == model_task_type)
        stmt = stmt.group_by(
            PPUQuotaUsage.tenant_id,
            PPUQuotaUsage.tier_id,
            PPUTier.name,
            PPUQuotaUsage.inference_name,
        )
        result = await self._db.execute(stmt)
        return result.all()
