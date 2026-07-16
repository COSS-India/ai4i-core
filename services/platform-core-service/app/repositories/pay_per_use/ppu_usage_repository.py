"""PPU usage repository — reads usage and accrued cost data."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier
from app.utils.billing_month import shift_billing_month


def _end_of_month(billing_month: str) -> datetime:
    """Last instant (UTC) of the given YYYY-MM billing month."""
    year, month = shift_billing_month(billing_month, 1)
    next_month_start = datetime(year, month, 1, tzinfo=timezone.utc)
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
        """One row per tenant: the tier assignment whose [effective_from, effective_to)
        window actually covers the end of billing_month. This may differ from the
        tenant's assignment as of "now" when the tenant has since moved to a different
        tier. A tenant with no assignment covering that instant — e.g. the current,
        still-in-progress month before any assignment has been made, or a gap between
        an expired assignment and the next one — is excluded entirely rather than
        surfacing a lapsed or not-yet-started assignment as their "current" tier.
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
            .where(
                PPUTenantTierAssignment.effective_from <= end_instant,
                PPUTenantTierAssignment.effective_to > end_instant,
            )
        )
        if tenant_id:
            ranked = ranked.where(PPUTenantTierAssignment.tenant_id == tenant_id)
        ranked = ranked.subquery()
        stmt = select(ranked).where(ranked.c.rn == 1)
        if tier_id:
            stmt = stmt.where(ranked.c.tier_id == tier_id)
        # Deterministic order: without this, ties (e.g. many tenants at spend=0) can come
        # back in a different order on every call, which breaks get_tenant_list's
        # pagination (same tenant duplicating across pages, or never appearing on any).
        stmt = stmt.order_by(ranked.c.tenant_id)
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

    async def get_total_cost_for_month(self, billing_month: str) -> Decimal:
        """Total cost_accum for billing_month, scoped to tenants with a tier assignment
        covering the END of that month — the same rule get_tenant_tier_as_of_period_end
        applies, via an EXISTS check instead of resolving the tenant list in Python.
        This scoping must match the current-month calculation's rule exactly: a tenant
        whose assignment window ended mid-month with no reassignment (a real, reachable
        case — assign_tier lets effective_to be any caller-supplied date, not just "far
        future") would otherwise be excluded when this month is queried as the current
        month but included here when it's queried as the previous month, making
        spendChangePercent reflect a scoping inconsistency rather than a real change.
        Still one query — used only when there's no tier_id filter, so an unfiltered
        total doesn't need the tenant-resolution step get_tenant_tier_usage_breakdown
        requires. Returned as Decimal (cost_accum is Numeric) — this codebase does money
        arithmetic in Decimal end-to-end to avoid float rounding error.
        """
        end_instant = _end_of_month(billing_month)
        has_coverage = exists(
            select(1).where(
                PPUTenantTierAssignment.tenant_id == PPUQuotaUsage.tenant_id,
                PPUTenantTierAssignment.effective_from <= end_instant,
                PPUTenantTierAssignment.effective_to > end_instant,
            )
        )
        stmt = select(func.sum(PPUQuotaUsage.cost_accum)).where(
            PPUQuotaUsage.billing_month == billing_month,
            has_coverage,
        )
        result = await self._db.execute(stmt)
        return result.scalar() or Decimal("0")

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
