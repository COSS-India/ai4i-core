"""PPU usage repository — reads usage and accrued cost data."""
import time
from decimal import Decimal

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.pay_per_use.budget_usage import BudgetUsage
from app.models.pay_per_use.quota_usage import QuotaUsage
from app.models.pay_per_use.tier import Tier


# get_tier_names() cache: UsageRepository is instantiated fresh per
# request, so this state has to live at module scope to survive across
# requests within the same process. TTL is configurable via
# PPU_TIER_CACHE_TTL_SECONDS (settings.ppu_tier_cache_ttl_seconds).
_tier_cache: dict[str, str] = {}
_tier_cache_loaded_at: float | None = None


def update_tier_cache(tier_id: str, name: str) -> None:
    """Write-through cache update so tier create/update/delete show up immediately, without waiting on the TTL."""
    _tier_cache[str(tier_id)] = name


class UsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_tenants_with_usage_tier(
        self,
        billing_month: str,
        tier_id: str | None = None,
        tenant_id: str | None = None,
        task_types: list[str] | None = None,
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
                QuotaUsage.tenant_id,
                QuotaUsage.tier_id,
                func.row_number()
                .over(
                    partition_by=QuotaUsage.tenant_id,
                    # tier_id as a tie-break makes the pick deterministic when two
                    # tiers share the same max(updated_at) down to the microsecond.
                    # nullslast() matters here: Postgres sorts NULL first under a plain
                    # DESC, which would let a deleted tier (tier_id IS NULL) win a tie
                    # over a real tier instead of only ever being the deliberate fallback.
                    order_by=(
                        func.max(QuotaUsage.updated_at).desc(),
                        QuotaUsage.tier_id.desc().nullslast(),
                    ),
                )
                .label("rn"),
            )
            .where(QuotaUsage.billing_month == billing_month)
            .group_by(QuotaUsage.tenant_id, QuotaUsage.tier_id)
        )
        # Query-level filter: only the task types the caller (frontend) requested.
        if task_types:
            ranked_activity = ranked_activity.where(
                QuotaUsage.inference_name.in_(task_types)
            )
        if tenant_id:
            ranked_activity = ranked_activity.where(QuotaUsage.tenant_id == tenant_id)
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
        """Placeholder: ppu_tenant_tier_assignments (the only source this
        used to read) is dropped, and its real replacement — reconstructing
        budget_limit/available_balance from tenants.allocated_budget and
        budget_usage across the two DBs — is being done in a separate,
        already-in-flight change. Not implemented here to avoid two PRs
        racing to define this method; every caller already tolerates an
        empty result (see usage_service._resolve_budget)."""
        return {}

    async def get_tenant_tier_usage_breakdown(
        self, billing_month: str, tenant_ids: list[str], task_types: list[str] | None = None
    ):
        """Per (tenant, tier, inference_name) usage/cost for the billing month, across
        every tier the tenant held that month — not just their most-recently-active tier.
        Filtered to ``task_types`` when the caller (frontend) passes them; otherwise the
        full breakdown is returned.
        """
        if not tenant_ids:
            return []
        stmt = (
            select(
                QuotaUsage.tenant_id,
                QuotaUsage.tier_id,
                QuotaUsage.inference_name,
                func.sum(QuotaUsage.monthly_quota_used).label("total_units"),
                # cost_accum was removed; total_cost will be sourced from
                # budget_usage.api_key_budget_used once that join is wired up.
                literal(0).label("total_cost"),
                func.max(QuotaUsage.monthly_quota_snap).label("quota_snap"),
            )
            .where(
                QuotaUsage.billing_month == billing_month,
                QuotaUsage.tenant_id.in_(tenant_ids),
            )
            .group_by(
                QuotaUsage.tenant_id,
                QuotaUsage.tier_id,
                QuotaUsage.inference_name,
            )
        )
        if task_types:
            stmt = stmt.where(QuotaUsage.inference_name.in_(task_types))
        result = await self._db.execute(stmt)
        return result.all()

    async def get_tier_names(self) -> dict:
        """{tier_id: name} for every tier, read straight from ppu_tiers.

        ppu_tiers is small and rarely changes, so callers resolve tier_name
        display labels from this map in Python rather than joining ppu_tiers
        into every ppu_quota_usage query — keeps get_tenants_with_usage_tier
        and get_tenant_tier_usage_breakdown genuinely single-table reads.

        Cached in-process for settings.ppu_tier_cache_ttl_seconds (default
        600s / 10 minutes, see PPU_TIER_CACHE_TTL_SECONDS): tier_name here is
        purely a display label (tier enforcement reads elsewhere), so
        cross-request staleness of up to that TTL is acceptable for a full
        reload. tier_service calls update_tier_cache() on create/rename/
        delete to write the changed entry through immediately in the worker
        that handled the request; other worker processes (this service runs
        multiple) still pick up the change within the TTL window.
        """
        global _tier_cache, _tier_cache_loaded_at
        now = time.monotonic()
        if (
            _tier_cache_loaded_at is not None
            and now - _tier_cache_loaded_at < settings.ppu_tier_cache_ttl_seconds
        ):
            return dict(_tier_cache)

        stmt = select(Tier.id, Tier.name)
        result = await self._db.execute(stmt)
        _tier_cache = {str(row.id): row.name for row in result.all()}
        _tier_cache_loaded_at = now
        return dict(_tier_cache)

    async def get_total_cost_for_month(self) -> Decimal:
        """Total api_key_budget_used across all API keys.

        budget_usage has no billing_month or inference_name column, so no
        per-month or per-task-type filtering is possible yet. Callers that
        need those dimensions must use get_tenant_tier_usage_breakdown instead.
        """
        stmt = select(func.sum(BudgetUsage.api_key_budget_used))
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
                QuotaUsage.tenant_id,
                QuotaUsage.tier_id,
                func.min(QuotaUsage.created_at).label("first_seen"),
            )
            .where(QuotaUsage.tenant_id.in_(tenant_ids))
            .group_by(QuotaUsage.tenant_id, QuotaUsage.tier_id)
        )
        result = await self._db.execute(stmt)
        return result.all()
