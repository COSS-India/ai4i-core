"""PPU usage repository — reads usage and accrued cost data."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier


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

    async def get_tenant_tier_usage_breakdown(self, billing_month: str, tenant_ids: list[str]):
        """Per (tenant, tier, inference_name) usage/cost for the billing month, across
        every tier the tenant held that month — not just their tier as of period end.
        Always unfiltered by task type: callers that need a single task type's numbers
        filter this result in Python so the full breakdown (spend/budget/tierBreakdown)
        stays consistent regardless of which task type is being drilled into.
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
            .group_by(
                PPUQuotaUsage.tenant_id,
                PPUQuotaUsage.tier_id,
                PPUTier.name,
                PPUQuotaUsage.inference_name,
            )
        )
        result = await self._db.execute(stmt)
        return result.all()

    async def get_tier_first_seen(self, tenant_ids: list[str]):
        """Earliest effective_from per (tenant_id, tier_id) — used to order a tenant's
        tierBreakdown chronologically (oldest tier first), regardless of how many times
        they've cycled on/off that tier since.
        """
        if not tenant_ids:
            return []
        stmt = (
            select(
                PPUTenantTierAssignment.tenant_id,
                PPUTenantTierAssignment.tier_id,
                func.min(PPUTenantTierAssignment.effective_from).label("first_seen"),
            )
            .where(PPUTenantTierAssignment.tenant_id.in_(tenant_ids))
            .group_by(PPUTenantTierAssignment.tenant_id, PPUTenantTierAssignment.tier_id)
        )
        result = await self._db.execute(stmt)
        return result.all()
