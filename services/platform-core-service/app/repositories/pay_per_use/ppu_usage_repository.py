"""PPU usage repository — reads usage and accrued cost data."""
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.pay_per_use.ppu_quota_usage import PPUQuotaUsage
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier
from app.utils.billing_month import shift_billing_month


def _end_of_month(billing_month: str) -> datetime:
    """Last instant (UTC) of the given YYYY-MM billing month."""
    year, month = shift_billing_month(billing_month, 1)
    next_month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    return next_month_start - timedelta(microseconds=1)


# get_tier_names() cache: PPUUsageRepository is instantiated fresh per
# request, so this state has to live at module scope to survive across
# requests within the same process. TTL is configurable via
# PPU_TIER_CACHE_TTL_SECONDS (settings.ppu_tier_cache_ttl_seconds).
_tier_cache: dict[str, str] = {}
_tier_cache_loaded_at: float | None = None


class PPUUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_tenants_with_usage_tier(
        self,
        billing_month: str,
        tier_id: str | None = None,
        tenant_id: str | None = None,
    ):
        """One row per tenant: the tier they were most recently active under
        this billing_month, derived entirely from ppu_quota_usage.

        ppu_tenant_tier_assignments is deliberately NOT used here —
        effective_from/effective_to on that table describe a BUDGET period
        (see assign_tier/reassign_tier), not tier-assignment validity, so
        they play no part in deciding which tenants/tiers appear. A tenant
        with zero ppu_quota_usage rows this billing_month has nothing to
        report and is excluded entirely (no synthetic zero-usage row).

        "Most recently active tier" = the tier_id with the latest
        updated_at among this tenant's usage rows this month — a tenant
        reassigned mid-month shows their newer tier here (tierBreakdown
        still lists every tier they actually used that month).
        """
        # row_number() evaluates after GROUP BY within the same SELECT, so the rank can
        # be computed directly alongside the max(updated_at) aggregate — no need for a
        # second subquery just to add it (matches the single-subquery shape
        # get_tenant_budgets already uses for the same "rank per tenant, keep rn==1"
        # pattern below).
        ranked_activity = (
            select(
                PPUQuotaUsage.tenant_id,
                PPUQuotaUsage.tier_id,
                func.row_number()
                .over(
                    partition_by=PPUQuotaUsage.tenant_id,
                    # tier_id as a tie-break makes the pick deterministic when two
                    # tiers share the same max(updated_at) down to the microsecond.
                    # nullslast() matters here: Postgres sorts NULL first under a plain
                    # DESC, which would let a deleted tier (tier_id IS NULL) win a tie
                    # over a real tier instead of only ever being the deliberate fallback.
                    order_by=(
                        func.max(PPUQuotaUsage.updated_at).desc(),
                        PPUQuotaUsage.tier_id.desc().nullslast(),
                    ),
                )
                .label("rn"),
            )
            .where(PPUQuotaUsage.billing_month == billing_month)
            .group_by(PPUQuotaUsage.tenant_id, PPUQuotaUsage.tier_id)
        )
        if tenant_id:
            ranked_activity = ranked_activity.where(PPUQuotaUsage.tenant_id == tenant_id)
        ranked = ranked_activity.subquery()

        stmt = select(
            ranked.c.tenant_id, ranked.c.tier_id
        ).where(ranked.c.rn == 1)
        if tier_id:
            stmt = stmt.where(ranked.c.tier_id == tier_id)
        # Deterministic order: without this, ties can come back in a different
        # order on every call, which breaks get_tenant_list's pagination (same
        # tenant duplicating across pages, or never appearing on any).
        stmt = stmt.order_by(ranked.c.tenant_id)
        result = await self._db.execute(stmt)
        return result.all()

    async def get_tenant_budgets(self, billing_month: str, tenant_ids: list[str]) -> dict:
        """budget_limit/available_balance/tier_id per tenant_id, read from whichever
        ppu_tenant_tier_assignments row was in effect at the END of
        billing_month.

        This is the one place ppu_tenant_tier_assignments is still read for
        the usage-tenant(s) endpoints — mainly for these budget columns,
        never to decide which tenants/tiers are shown when there's usage
        (that comes from get_tenants_with_usage_tier). tier_id is only
        consumed by get_tenant_detail's zero-usage fallback, to show a
        tenant's actual assigned tier instead of "Unassigned" when they
        simply have no usage yet this billing_month. A tenant with no
        assignment covering that instant is simply absent from the returned
        dict; callers treat that as budget_limit=0/available_balance=0.
        """
        if not tenant_ids:
            return {}
        end_instant = _end_of_month(billing_month)
        ranked = (
            select(
                PPUTenantTierAssignment.tenant_id,
                PPUTenantTierAssignment.tier_id,
                PPUTenantTierAssignment.budget_limit,
                PPUTenantTierAssignment.available_balance,
                func.row_number()
                .over(
                    partition_by=PPUTenantTierAssignment.tenant_id,
                    order_by=PPUTenantTierAssignment.effective_from.desc(),
                )
                .label("rn"),
            )
            .where(
                PPUTenantTierAssignment.effective_from <= end_instant,
                PPUTenantTierAssignment.effective_to > end_instant,
                PPUTenantTierAssignment.tenant_id.in_(tenant_ids),
            )
        ).subquery()
        stmt = select(ranked).where(ranked.c.rn == 1)
        result = await self._db.execute(stmt)
        return {row.tenant_id: row for row in result.all()}

    async def get_tenant_tier_usage_breakdown(self, billing_month: str, tenant_ids: list[str]):
        """Per (tenant, tier, inference_name) usage/cost for the billing month, across
        every tier the tenant held that month — not just their most-recently-active tier.
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
                PPUQuotaUsage.inference_name,
                func.sum(PPUQuotaUsage.units_used).label("total_units"),
                func.sum(PPUQuotaUsage.cost_accum).label("total_cost"),
                func.max(PPUQuotaUsage.monthly_quota_snap).label("quota_snap"),
            )
            .where(
                PPUQuotaUsage.billing_month == billing_month,
                PPUQuotaUsage.tenant_id.in_(tenant_ids),
            )
            .group_by(
                PPUQuotaUsage.tenant_id,
                PPUQuotaUsage.tier_id,
                PPUQuotaUsage.inference_name,
            )
        )
        result = await self._db.execute(stmt)
        return result.all()

    async def get_tier_names(self) -> dict:
        """{tier_id: name} for every tier, read straight from ppu_tiers.

        ppu_tiers is small and rarely changes, so callers resolve tier_name
        display labels from this map in Python rather than joining ppu_tiers
        into every ppu_quota_usage query — keeps get_tenants_with_usage_tier
        and get_tenant_tier_usage_breakdown genuinely single-table reads.

        Cached in-process for settings.ppu_tier_cache_ttl_seconds (default
        3600s / 1 hour, see PPU_TIER_CACHE_TTL_SECONDS): tier_name here is
        purely a display label (tier enforcement reads elsewhere), so
        cross-request staleness of up to that TTL is acceptable. There is
        no invalidation hook from tier_service.update_tier, so a tier
        rename can take up to the full TTL to show up on the dashboard.
        """
        global _tier_cache, _tier_cache_loaded_at
        now = time.monotonic()
        if (
            _tier_cache_loaded_at is not None
            and now - _tier_cache_loaded_at < settings.ppu_tier_cache_ttl_seconds
        ):
            return dict(_tier_cache)

        stmt = select(PPUTier.id, PPUTier.name)
        result = await self._db.execute(stmt)
        _tier_cache = {str(row.id): row.name for row in result.all()}
        _tier_cache_loaded_at = now
        return dict(_tier_cache)

    async def get_total_cost_for_month(self, billing_month: str) -> Decimal:
        """Total cost_accum for billing_month, across every tenant that has
        usage that month. No tenant scoping beyond the billing_month filter
        is needed: "active tenant" is now simply "has a ppu_quota_usage row
        this month", so every row in scope already belongs to an active
        tenant by definition. Returned as Decimal (cost_accum is Numeric) —
        this codebase does money arithmetic in Decimal end-to-end to avoid
        float rounding error.
        """
        stmt = select(func.sum(PPUQuotaUsage.cost_accum)).where(
            PPUQuotaUsage.billing_month == billing_month
        )
        result = await self._db.execute(stmt)
        return result.scalar() or Decimal("0")

    async def get_tier_first_seen(self, tenant_ids: list[str]):
        """Earliest ppu_quota_usage activity per (tenant_id, tier_id), across
        all billing months — used to order a tenant's tierBreakdown
        chronologically (oldest tier first), regardless of how many times
        they've cycled on/off that tier since. Derived from usage, not
        ppu_tenant_tier_assignments: assignment effective_from/effective_to
        describe budget periods, not when a tenant actually started using a
        tier.
        """
        if not tenant_ids:
            return []
        stmt = (
            select(
                PPUQuotaUsage.tenant_id,
                PPUQuotaUsage.tier_id,
                func.min(PPUQuotaUsage.created_at).label("first_seen"),
            )
            .where(PPUQuotaUsage.tenant_id.in_(tenant_ids))
            .group_by(PPUQuotaUsage.tenant_id, PPUQuotaUsage.tier_id)
        )
        result = await self._db.execute(stmt)
        return result.all()
