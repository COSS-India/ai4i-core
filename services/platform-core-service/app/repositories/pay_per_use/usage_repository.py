"""PPU usage repository — reads usage and accrued cost data."""
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.pay_per_use.budget_usage import BudgetUsage
from app.models.pay_per_use.quota_usage import QuotaUsage
from app.models.pay_per_use.tier import Tier
from app.utils.billing_month import shift_billing_month


def _end_of_month(billing_month: str) -> datetime:
    """Last instant (UTC) of the given YYYY-MM billing month."""
    year, month = shift_billing_month(billing_month, 1)
    next_month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    return next_month_start - timedelta(microseconds=1)


def _budget_lookup_instant(billing_month: str) -> datetime:
    """Instant to check assignment coverage against for a given billing_month.

    For the current, still-open month there is no "end of month" yet, so we
    need the tenant's budget as of right now — matching the instant
    _lock_active_assignment uses when top-up/top-down writes to this same
    table. For a past, closed month, _end_of_month gives the correct frozen
    snapshot. Using _end_of_month for the current month would require an
    assignment's effective_to to already reach the last microsecond of a
    month that hasn't happened yet, which real assignment windows (typically
    written as midnight on their intended last day) never satisfy — that
    mismatch was showing budgets as 0 for tenants with a perfectly valid,
    currently-active assignment.
    """
    now = datetime.now(timezone.utc)
    current_billing_month = f"{now.year:04d}-{now.month:02d}"
    if billing_month == current_billing_month:
        return now
    return _end_of_month(billing_month)


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
        billing_month: str | None,
        tier_id: str | None = None,
        tenant_id: str | None = None,
        task_types: list[str] | None = None,
    ):
        """One row per tenant: the tier they were most recently active under
        this billing_month, derived entirely from ppu_quota_usage. billing_month=None
        means all-time (no month filter) — "most recently active tier" then becomes
        the tier with the latest updated_at across the tenant's entire usage history.

        ppu_tenant_tier_assignments is deliberately NOT used here —
        effective_from/effective_to on that table describe a BUDGET period
        (see assign_tier/reassign_tier), not tier-assignment validity, so
        they play no part in deciding which tenants/tiers appear. A tenant
        with zero ppu_quota_usage rows in scope has nothing to
        report and is excluded entirely (no synthetic zero-usage row).

        "Most recently active tier" = the tier_id with the latest
        updated_at among this tenant's in-scope usage rows — a tenant
        reassigned mid-month shows their newer tier here (tierBreakdown
        still lists every tier they actually used in scope).
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
            .group_by(QuotaUsage.tenant_id, QuotaUsage.tier_id)
        )
        if billing_month is not None:
            ranked_activity = ranked_activity.where(QuotaUsage.billing_month == billing_month)
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

    async def get_tenant_budgets(
        self,
        billing_month: str | None,
        tenant_ids: list[str],
        auth_db: Optional[AsyncSession] = None,
    ) -> dict:
        """budget_limit/available_balance/tier_id/budget_effective_from/
        budget_effective_to per tenant_id.

        ppu_tenant_tier_assignments was dropped (AI4IDS-2923) when billing moved to
        per-API-key budget_usage deduction — reconstructed here from tables that
        still exist, split across two databases the same way _resolve_tenant_names
        already does:
          - budget_limit = tenants.allocated_budget (auth-service, via auth_db)
          - available_balance = budget_limit - SUM(budget_usage.api_key_budget_used)
            across every api_key belonging to one of the tenant's applications
            (api_key/applications live in auth-service too; budget_usage is local)
          - tier_id = tenants.tier_id (auth-service) — matches the old contract
            exactly: this was ONLY ever consumed by get_tenant_detail's zero-usage
            fallback, never to decide which tenants/tiers have usage (that's
            get_tenants_with_usage_tier, sourced from ppu_quota_usage, unaffected
            by any of this).
          - budget_effective_from/budget_effective_to = tenants.budget_effective_from/
            budget_effective_to (auth-service) — NOT the same thing as the dropped
            ppu_tenant_tier_assignments row's effective_from/to window mentioned
            below; these live directly on tenants, are set once at tenant creation
            (TenantService.create_tenant), and are untouched by budget top-up/
            top-down (TenantService.revise_tenant_budget only updates
            allocated_budget) — nullable, so absent for any tenant created before
            these columns existed or without a configured budget window.

        billing_month is accepted for interface compatibility but no longer
        narrows this particular lookup: budget_usage carries no per-month
        dimension (a single lifetime-cumulative row per key, unlike the old
        assignment row's effective_from/to window), so for a PAST billing_month
        this now reflects the tenant's CURRENT balance, not a frozen snapshot as
        of that month's end. Accepted, not fixed here — that's a schema gap
        upstream of this repository (see budget_usage's model), not something
        reconstructable from data that was never captured.

        A tenant not found in auth-service's tenants table (unknown tenant_id,
        or the auth_db param itself not passed/None), OR found but with
        allocated_budget still NULL (never had a budget configured — the column
        is nullable), is simply absent from the returned dict, same as the old
        "no assignment row" case — callers already treat that as
        budget_limit=0/available_balance=0/has_budget=False via _resolve_budget.
        Coalescing a NULL allocated_budget to 0 here instead would make
        has_budget=True for a tenant with no budget on file, which is the
        "unknown vs. genuinely zero" mixup _resolve_budget's own docstring says
        must not happen.

        A query against auth_db that raises (connection drop, aborted
        transaction) is NOT one of those graceful-degrade cases and is left to
        propagate — see application_usage_service._load_tenant_budget for the
        same rule. Swallowing it here would turn a DB outage into a false
        all-tenants-zero-budget response instead of the 500 it should be.
        """
        if not tenant_ids or not auth_db:
            return {}
        numeric_ids = [int(t) for t in tenant_ids if t and t.isdigit()]
        if not numeric_ids:
            return {}
        # No try/except around this auth_db lookup: a query that raises here is a
        # real failure (connection drop, aborted transaction), not "no budget on
        # file" — swallowing it would silently turn a DB outage into a false
        # all-tenants-zero-budget response (see application_usage_service's
        # _load_tenant_budget for the same rule already applied there). Let it
        # propagate; the global exception handler turns it into a proper 500.
        tenant_rows = (
            await auth_db.execute(
                text(
                    "SELECT id, allocated_budget, tier_id, budget_effective_from, "
                    "budget_effective_to FROM tenants WHERE id = ANY(:ids)"
                ),
                {"ids": numeric_ids},
            )
        ).all()
        if not tenant_rows:
            return {}

        app_rows = (
            await auth_db.execute(
                text("SELECT id, tenant_id FROM applications WHERE tenant_id = ANY(:ids)"),
                {"ids": [row.id for row in tenant_rows]},
            )
        ).all()
        app_to_tenant = {row.id: row.tenant_id for row in app_rows}

        key_to_tenant: dict[int, int] = {}
        if app_to_tenant:
            key_rows = (
                await auth_db.execute(
                    text("SELECT id, application_id FROM api_key WHERE application_id = ANY(:app_ids)"),
                    {"app_ids": list(app_to_tenant)},
                )
            ).all()
            for row in key_rows:
                tenant_for_key = app_to_tenant.get(row.application_id)
                if tenant_for_key is not None:
                    key_to_tenant[row.id] = tenant_for_key

        spent_by_tenant: dict[int, Decimal] = {}
        if key_to_tenant:
            spend_stmt = select(BudgetUsage.api_key_id, BudgetUsage.api_key_budget_used).where(
                BudgetUsage.api_key_id.in_(key_to_tenant)
            )
            spend_rows = (await self._db.execute(spend_stmt)).all()
            for row in spend_rows:
                tenant_for_key = key_to_tenant.get(row.api_key_id)
                if tenant_for_key is not None:
                    spent_by_tenant[tenant_for_key] = spent_by_tenant.get(
                        tenant_for_key, Decimal("0")
                    ) + (row.api_key_budget_used or Decimal("0"))

        budgets: dict[str, SimpleNamespace] = {}
        for row in tenant_rows:
            if row.allocated_budget is None:
                # No budget configured for this tenant — leave them absent from the
                # dict so _resolve_budget reports has_budget=False (unknown), not a
                # real allocated_budget=0 (genuinely zero and therefore "exceeded").
                continue
            budget_limit = row.allocated_budget
            spent = spent_by_tenant.get(row.id, Decimal("0"))
            budgets[str(row.id)] = SimpleNamespace(
                tenant_id=str(row.id),
                tier_id=row.tier_id,
                budget_limit=budget_limit,
                available_balance=budget_limit - spent,
                spent=spent,
                budget_effective_from=row.budget_effective_from,
                budget_effective_to=row.budget_effective_to,
            )
        return budgets

    async def get_tenant_tier_usage_breakdown(
        self, billing_month: str | None, tenant_ids: list[str], task_types: list[str] | None = None
    ):
        """Per (tenant, tier, inference_name) usage, across every tier the tenant
        held in scope — not just their most-recently-active tier. billing_month=None
        means all-time: consumed sums across every month the tenant held that
        tier, while quota_snap (MAX, not SUM) still reflects that tier's own quota
        amount rather than double-counting it per month.
        Filtered to ``task_types`` when the caller (frontend) passes them; otherwise the
        full breakdown is returned.

        No cost/spend column here (and never one — this was `literal(0)` before,
        a placeholder for a `cost_accum` column dropped from ppu_quota_usage and
        never replaced): ppu_quota_usage has no per-task-type/per-tier money
        dimension, only unit counts. Real spend is tenant-level only, sourced from
        budget_usage.api_key_budget_used via get_tenant_budgets — see that
        method's docstring and UsageService._build_hierarchical_item.
        """
        if not tenant_ids:
            return []
        stmt = (
            select(
                QuotaUsage.tenant_id,
                QuotaUsage.tier_id,
                QuotaUsage.inference_name,
                func.sum(QuotaUsage.monthly_quota_used).label("total_units"),
                func.max(QuotaUsage.monthly_quota_snap).label("quota_snap"),
            )
            .where(QuotaUsage.tenant_id.in_(tenant_ids))
            .group_by(
                QuotaUsage.tenant_id,
                QuotaUsage.tier_id,
                QuotaUsage.inference_name,
            )
        )
        if billing_month is not None:
            stmt = stmt.where(QuotaUsage.billing_month == billing_month)
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
