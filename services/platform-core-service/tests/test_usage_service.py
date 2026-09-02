"""Unit tests for UsageService — hierarchical tenant/tier/task-type aggregation.

All DB I/O is mocked via AsyncMock; no running services required.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.utils.billing_month as billing_month_module
from app.services.pay_per_use.usage_service import UsageService


def _freeze_now(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    """Pin billing_month_module's datetime.now() so current_billing_month() is
    deterministic (used by get_tenant_list/get_tenant_detail's all-time quota
    scoping)."""

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(billing_month_module, "datetime", _FrozenDateTime)


class _Seq(list):
    """Marks a list of per-call return values, applied via AsyncMock(side_effect=...),
    for methods invoked more than once with different args in a single service call
    (e.g. get_tenant_tier_usage_breakdown, hit for both the current and the previous
    billing month inside get_summary)."""


def _make_repo(**method_returns) -> MagicMock:
    """Return a mock repository whose async methods return the given values.

    get_tier_names defaults to the {tier_id: name} map matching _tier_row/_usage_row's
    own defaults ("1" -> "Pro", "2" -> "Enterprise" for the multi-tier tests), since
    tier_name resolution now happens via this map rather than a column on the row —
    override it explicitly for tests that need a different mapping.

    get_tenant_budgets defaults to {} (no budget row for anyone) — get_tenant_detail's
    zero-usage branch calls this unconditionally now to resolve a fallback tier, so
    tests that don't care about budgets would otherwise need to mock it just to avoid
    an unconfigured-MagicMock-isn't-awaitable error.
    """
    repo = MagicMock()
    method_returns.setdefault("get_tier_names", {"1": "Pro", "2": "Enterprise"})
    method_returns.setdefault("get_tenant_budgets", {})
    for method, value in method_returns.items():
        if isinstance(value, _Seq):
            setattr(repo, method, AsyncMock(side_effect=list(value)))
        else:
            setattr(repo, method, AsyncMock(return_value=value))
    return repo


def _row(**kwargs):
    """Lightweight stand-in for a SQLAlchemy Row."""
    return SimpleNamespace(**kwargs)


def _tier_row(**kwargs):
    """Stand-in for a get_tenants_with_usage_tier row — tier info only, derived from
    ppu_quota_usage. No budget fields; budget is a separate get_tenant_budgets lookup."""
    defaults = dict(tenant_id="t1", tier_id="1", tier_name="Pro")
    return _row(**{**defaults, **kwargs})


def _budget_row(**kwargs):
    """Stand-in for a get_tenant_budgets value — budget_limit/available_balance/spent/
    tier_id/budget_effective_from/budget_effective_to, read from tenants+budget_usage
    (auth-service + local). tier_id is only consumed by get_tenant_detail's zero-usage
    fallback (to show the tenant's actual assigned tier instead of "Unassigned");
    budget_effective_from/to are only consumed by get_tenant_detail's
    TenantBudgetDetail.budgetEffectiveFrom/To. spent is the REAL, tenant-total spend
    (sum of budget_usage.api_key_budget_used) that `spend`/`budget.spent`/
    `budget.percentageUsed` are now sourced from everywhere — defaults to 300 here so
    available_balance (700) + spent (300) == budget_limit (1000), matching what the
    real repository query would produce."""
    defaults = dict(
        tenant_id="t1", budget_limit=Decimal("1000"), available_balance=Decimal("700"),
        spent=Decimal("300"),
        tier_id="1", budget_effective_from=None, budget_effective_to=None,
    )
    return _row(**{**defaults, **kwargs})


def _budgets(*rows) -> dict:
    return {r.tenant_id: r for r in rows}


# Catalogue ids for the names these tests use. The repository projects
# task_type (coalesced name) and task_type_unit alongside inference_type_id, so
# the fixture has to carry all three or the service reads attributes that the
# real row would have.
_TYPE_IDS = {"llm": 1, "asr": 2, "nmt": 3, "tts": 4}
_TYPE_UNITS = {"llm": "tokens", "asr": "audio_minutes", "nmt": "characters", "tts": "characters"}


def _usage_row(**kwargs):
    """One row as get_tenant_tier_usage_breakdown projects it.

    Accepts ``task_type=`` (a name) and derives inference_type_id/task_type_unit
    from it, so callers keep reading naturally. Pass ``inference_type_id=None``
    explicitly to simulate a pre-catalogue row.
    """
    task_type = kwargs.pop("task_type", "llm")
    defaults = dict(
        tenant_id="t1", tier_id="1", tier_name="Pro",
        inference_type_id=_TYPE_IDS.get(task_type),
        task_type=task_type,
        task_type_unit=_TYPE_UNITS.get(task_type),
        total_units=100.0, total_cost=Decimal("50"),
        quota_snap=200.0,
    )
    return _row(**{**defaults, **kwargs})


# ── get_summary ───────────────────────────────────────────────────────────────

class TestGetSummary:
    """get_summary's totalSpend/budgetExceededTenants are real (sum of
    budget_usage.api_key_budget_used via get_tenant_budgets/_resolve_spent) and
    always lifetime-cumulative — billing_month never scopes them, matching every
    other spend figure in this service (see get_summary's own docstring).
    """

    @pytest.mark.asyncio
    async def test_total_spend_and_active_tenants(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(_budget_row(spent=Decimal("50"))),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.totalSpend == 50.0
        assert result.activeTenants == 1
        assert result.spendByModelTaskType[0].consumption == 100.0

    @pytest.mark.asyncio
    async def test_spend_item_has_no_spend_or_percentage_field(self):
        """Regression: SpendItem used to carry spend/percentage sourced from
        ppu_quota_usage's dropped cost_accum column (always 0, a silent lie) — there
        is no per-task-type money column anywhere, so these fields are removed
        entirely rather than continuing to show a fake number."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(task_type="llm"),
                _usage_row(task_type="asr"),
            ],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert len(result.spendByModelTaskType) == 2
        assert not hasattr(result.spendByModelTaskType[0], "spend")
        assert not hasattr(result.spendByModelTaskType[0], "percentage")

    @pytest.mark.asyncio
    async def test_budget_exceeded_tenant_is_counted(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(_budget_row(budget_limit=Decimal("10"), spent=Decimal("50"))),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.budgetExceededTenants == 1

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_row_is_not_falsely_exceeded(self):
        """A tenant with usage but no ppu_tenant_tier_assignments row covering this
        period's end has no budget figure at all — must not be treated as budget=0
        and therefore always 'exceeded' the moment they have any spend."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(),  # no row for t1
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        # unknown budget != a budget of 0 -- excluded from the count, not flagged as
        # exceeded, matching the 0%-used (not "over budget") treatment in the tenant
        # list/detail view for the same missing-budget-row case (see _resolve_budget).
        assert result.budgetExceededTenants == 0

    @pytest.mark.asyncio
    async def test_no_spend_change_percent_field(self):
        """Regression: spendChangePercent used to compare a (bugged, always-0)
        "current month" cost sum against get_total_cost_for_month's real-but-
        differently-scoped (global, all-time) total — comparing a fake number to a
        real one, already meaningless before this fix. Now that totalSpend is real,
        it's also always lifetime-cumulative (budget_usage has no per-month
        dimension), so there is no "this month vs last month" to ever compute — the
        field is removed entirely (not kept as a permanently-null one), even with
        substantial real spend present."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(_budget_row(spent=Decimal("500"))),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.totalSpend == 500.0
        assert not hasattr(result, "spendChangePercent")

    @pytest.mark.asyncio
    async def test_omitted_billing_period_defaults_to_all_time_not_current_month(self):
        """Regression: billing_period=None used to collapse to the current calendar
        month before reaching the repository, silently narrowing the dashboard's
        "up to now" figure to whatever's happened since the 1st. It must now reach
        the repository as None (all-time, no month filter) instead."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(_budget_row(spent=Decimal("50"))),
        )
        svc = UsageService(repo)
        result = await svc.get_summary(None)

        assert result.totalSpend == 50.0
        # null, not a sentinel string like "lifetime" — billing_period is validated
        # against ^\d{4}-(0[1-9]|1[0-2])$ on every /usage-* route, so a client echoing
        # this value back as billing_period must get something that round-trips
        # (omitted == all-time again), not a value that 422s.
        assert result.billingPeriod is None
        repo.get_tenants_with_usage_tier.assert_called_once_with(None, None, task_type_ids=None)
        repo.get_tenant_tier_usage_breakdown.assert_called_once_with(None, ["t1"], task_type_ids=None)

    @pytest.mark.asyncio
    async def test_billing_period_response_value_is_valid_query_input_elsewhere(self):
        """Regression: a client calling GET /usage-summary with no billing_period used
        to get back billingPeriod="lifetime" in the response. Every /usage-* route
        (including /usage-tenant and /usage-tenants) validates its billing_period
        query param against ^\\d{4}-(0[1-9]|1[0-2])$ — "lifetime" fails that pattern,
        so a client echoing the response value back in as billing_period=lifetime
        would get a 422 instead of the all-time view it asked for. The fix must
        return a value a client CAN legally pass back: None, which every route
        already treats as "omit the param" == all-time."""
        # Same pattern the three routes use (app/routes/usage.py) — kept inline so this
        # test still fails if that pattern ever changes without this assertion being
        # revisited, rather than importing it and silently tracking any drift.
        billing_period_pattern = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_summary(None)

        # The old sentinel would have failed the very pattern it needed to round-trip
        # through — confirms this was a real, reachable bug, not a hypothetical one.
        assert not billing_period_pattern.match("lifetime")
        assert result.billingPeriod is None

    @pytest.mark.asyncio
    async def test_omitted_billing_period_has_no_spend_change_percent(self):
        """Same as test_no_spend_change_percent_field, for the omitted-billing_period
        (all-time) path specifically — the field's absence doesn't depend on
        billing_month at all, but this locks in that the all-time path doesn't
        somehow reintroduce it."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_summary(None)

        assert not hasattr(result, "spendChangePercent")

    @pytest.mark.asyncio
    async def test_allocated_and_remaining_budget_summed_across_tenants(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row(tenant_id="t1"), _tier_row(tenant_id="t2")],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1"),
                _usage_row(tenant_id="t2"),
            ],
            get_tenant_budgets=_budgets(
                _budget_row(tenant_id="t1", budget_limit=Decimal("1000"), available_balance=Decimal("700")),
                _budget_row(tenant_id="t2", budget_limit=Decimal("500"), available_balance=Decimal("200")),
            ),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.totalAllocatedBudget == 1500.0
        assert result.totalRemainingBudget == 900.0

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_row_excluded_from_budget_totals(self):
        """Same "unknown limit != 0" treatment as budgetExceededTenants — a tenant
        with no assignment row on file must not contribute a 0 to either total."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(),  # no row for t1
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.totalAllocatedBudget == 0.0
        assert result.totalRemainingBudget == 0.0

    @pytest.mark.asyncio
    async def test_spend_item_allocated_summed_across_tenants_current_tier(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row(tenant_id="t1"), _tier_row(tenant_id="t2", tier_id="2")],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", tier_id="1", total_units=100.0, quota_snap=200.0),
                _usage_row(tenant_id="t2", tier_id="2", total_units=50.0, quota_snap=300.0),
            ],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        llm_item = next(i for i in result.spendByModelTaskType if i.modelTaskType == "llm")
        assert llm_item.consumption == 150.0
        assert llm_item.allocated == 500.0

    @pytest.mark.asyncio
    async def test_spend_item_allocated_null_when_no_quota_snapshot(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row(quota_snap=None)],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.spendByModelTaskType[0].allocated is None

    @pytest.mark.asyncio
    async def test_spend_item_allocated_populated_independently_per_task_type(self):
        """Unlike a single flat total (which can only ever hold one unit), each
        SpendItem carries its own allocated figure — LLM and ASR can both show
        allocated at once, in their own units, on the same unfiltered call."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(task_type="llm", total_units=100.0, quota_snap=200.0),
                _usage_row(task_type="asr", total_units=10.0, quota_snap=50.0),
            ],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        by_type = {i.modelTaskType: i for i in result.spendByModelTaskType}
        assert by_type["llm"].allocated == 200.0
        assert by_type["asr"].allocated == 50.0

    @pytest.mark.asyncio
    async def test_spend_item_allocated_excludes_quota_from_non_current_tier(self):
        """Quota isn't cumulative across tiers a tenant held mid-period — only the
        row matching the tenant's CURRENT (end-of-period) tier counts toward
        allocated, though consumption still sums across every tier they used."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row(tier_id="2")],  # current tier is "2"
            get_tenant_tier_usage_breakdown=[
                _usage_row(tier_id="1", total_units=100.0, quota_snap=500.0),  # old tier, excluded
                _usage_row(tier_id="2", total_units=50.0, quota_snap=100.0),  # current tier, counted
            ],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.spendByModelTaskType[0].consumption == 150.0
        assert result.spendByModelTaskType[0].allocated == 100.0


class TestGetSummaryFiltered:
    """get_summary(tier_id=<id>) scopes tenant selection (and therefore totalSpend/
    budgetExceededTenants) by "who was on this tier," not by usage row."""

    @pytest.mark.asyncio
    async def test_total_spend_real_with_tier_id_set(self):
        """totalSpend behaves the same real/lifetime way whether or not tier_id
        narrows tenant selection — tier_id only changes WHICH tenants are in scope
        (via get_tenants_with_usage_tier), not how their spend is sourced (see
        get_summary's docstring)."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(_budget_row(spent=Decimal("150"))),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06", tier_id="1")

        assert result.totalSpend == 150.0
        assert not hasattr(result, "spendChangePercent")
        repo.get_tenants_with_usage_tier.assert_called_once_with("2026-06", "1", task_type_ids=None)


# ── get_tenant_list ───────────────────────────────────────────────────────────

class TestGetTenantList:
    @pytest.mark.asyncio
    async def test_spend_reflects_real_budget_usage_not_hardcoded_zero(self):
        """Regression: `spend`/`budget.spent`/`budget.percentageUsed` used to always
        be 0 — get_tenant_tier_usage_breakdown's total_cost was `literal(0)`, a
        placeholder for a dropped cost_accum column that was never replaced. They
        must now reflect the real sum of budget_usage.api_key_budget_used across the
        tenant's api keys (get_tenant_budgets), completely independent of whatever
        usage_rows' now-nonexistent cost data might have said."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row(
                budget_limit=Decimal("10000"), spent=Decimal("4321"),
            )),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.spend == 4321.0
        assert item.budget.spent == 4321.0
        assert item.budget.percentageUsed == 43.2  # 4321 / 10000 * 100, rounded

    @pytest.mark.asyncio
    async def test_single_tenant_single_tier_single_task_type(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row()),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        assert result.total == 1
        item = result.data[0]
        assert item.tenantId == "t1"
        assert item.tier == "Pro"
        assert item.spend == 300.0
        assert item.budget.limit == 1000.0
        assert item.budget.remaining == 700.0
        # single distinct task type -> auto-populated even without a filter
        assert item.usage.taskTypeCount == 1
        assert item.usage.consumed == 100.0
        assert item.usage.quotaLimit == 200.0
        assert len(item.tierBreakdown) == 1
        # No spend/percentage on taskTypes (or tierBreakdown itself) at either
        # endpoint any more — no table backs per-task-type/per-tier cost (see
        # TierUsageBreakdown/TaskTypeUsage's own schema docstrings).
        assert not hasattr(item.tierBreakdown[0], "spend")
        assert not hasattr(item.tierBreakdown[0].taskTypes[0], "spend")
        assert not hasattr(item.tierBreakdown[0].taskTypes[0], "percentage")
        # budgetEffectiveFrom/To are /usage-tenant-only (TenantBudgetDetail) — the
        # list endpoint's budget stays a plain TenantBudget without them.
        assert not hasattr(item.budget, "budgetEffectiveFrom")
        assert not hasattr(item.budget, "budgetEffectiveTo")

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_row_shows_zero_budget(self):
        """A tenant with usage this month but no ppu_tenant_tier_assignments row
        covering this period's end must show budget=0, not error/crash."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.budget.limit == 0.0
        assert item.budget.remaining == 0.0

    @pytest.mark.asyncio
    async def test_remaining_quota_clamped_at_zero_when_overused(self):
        """remaining must never go negative, even when consumed exceeds the quota —
        both on the flat `usage` block and on each tierBreakdown taskType entry."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(total_units=150.0, quota_snap=100.0),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.usage.remaining == 0.0
        assert item.tierBreakdown[0].taskTypes[0].remaining == 0.0

    @pytest.mark.asyncio
    async def test_quota_populated_when_current_tier_is_deleted(self):
        """A tenant whose current tier was deleted (ON DELETE SET NULL on the FK) has
        tier_id=None on both the assignment and the matching usage row. The lookup that
        matches them must treat None consistently on both sides — previously it compared
        str(None) == "unassigned" and never matched, silently dropping quota/remaining/
        percentage even though quota_snap data existed on the row."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row(tier_id=None, tier_name=None)],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tier_id=None, tier_name=None, total_units=50.0, quota_snap=200.0),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        usage = result.data[0].usage
        assert usage.quotaLimit == 200.0
        assert usage.consumed == 50.0
        assert usage.remaining == 150.0

    @pytest.mark.asyncio
    async def test_zero_quota_with_usage_shows_fully_exhausted(self):
        """A 0 quota is a deliberate 'blocked for this cycle' setting, not missing data.
        Any usage against it must show percentage=100, not 0 (which `if quota` would
        give since 0.0 is falsy)."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(total_units=5.0, quota_snap=0.0),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        usage = result.data[0].usage
        assert usage.quotaLimit == 0.0
        assert usage.remaining == 0.0
        assert usage.percentage == 100.0

    @pytest.mark.asyncio
    async def test_zero_quota_with_no_usage_shows_zero_percent(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(total_units=0.0, quota_snap=0.0),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        assert result.data[0].usage.percentage == 0.0

    @pytest.mark.asyncio
    async def test_multi_tier_breakdown_ordered_oldest_first(self):
        """A tenant reassigned mid-period shows both tiers, oldest tier first, and spend
        is the sum across every tier they held that month."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row(tier_id="2", tier_name="Enterprise")],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tier_id="1", tier_name="Pro"),
                _usage_row(tier_id="2", tier_name="Enterprise"),
            ],
            get_tier_first_seen=[
                _row(tenant_id="t1", tier_id="2", first_seen=datetime(2026, 6, 15, tzinfo=timezone.utc)),
                _row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 6, 1, tzinfo=timezone.utc)),
            ],
            get_tenant_budgets=_budgets(_budget_row(spent=Decimal("50"))),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.spend == 50.0
        assert [tb.tierId for tb in item.tierBreakdown] == ["1", "2"]

    @pytest.mark.asyncio
    async def test_omitted_billing_month_keeps_quota_current_month_but_spend_all_time(self, monkeypatch):
        """Regression: billing_month=None ("all-time") must widen spend/budget to a
        lifetime total, but quota (consumed/quotaLimit/remaining/percentage) resets
        monthly and must stay scoped to the current month. Before this fix, quota's
        `consumed` was summed across every month (like spend) while `quotaLimit`
        stayed a single month's grant — 6 months of normal usage (600 units against a
        100-unit monthly grant) would report percentage=600.0 instead of 100.0."""
        _freeze_now(monkeypatch, datetime(2026, 6, 15, tzinfo=timezone.utc))
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=_Seq([
                # all-time call (billing_month=None): 6 months of usage summed
                [_usage_row(total_units=600.0, total_cost=Decimal("300"), quota_snap=100.0)],
                # current-month-only call (billing_month="2026-06"): just this month
                [_usage_row(total_units=100.0, total_cost=Decimal("50"), quota_snap=100.0)],
            ]),
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row(budget_limit=Decimal("10000"), available_balance=Decimal("9700"))),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list(None, None, None, auth_db=None)

        item = result.data[0]
        assert item.spend == 300.0  # lifetime total, unaffected by the quota fix
        assert item.usage.consumed == 100.0  # current month only, not the 600 lifetime total
        assert item.usage.quotaLimit == 100.0
        assert item.usage.percentage == 100.0  # not 600.0
        assert item.usage.remaining == 0.0

        assert repo.get_tenant_tier_usage_breakdown.call_count == 2
        first_call, second_call = repo.get_tenant_tier_usage_breakdown.call_args_list
        assert first_call.args[0] is None
        assert second_call.args[0] == "2026-06"

    @pytest.mark.asyncio
    async def test_given_billing_month_scopes_quota_only_budget_stays_all_time(self):
        """Even when billing_month is given explicitly (not omitted), budget/spend/
        tierBreakdown always come from an all-time query — only quota is scoped to
        the given month. This always issues two get_tenant_tier_usage_breakdown
        calls: one for None (budget), one for the given month (quota). spend itself
        comes from get_tenant_budgets (real, tenant-total, always all-time), NOT
        from either usage_rows query — see _build_hierarchical_item's docstring."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=_Seq([
                # all-time call (tierBreakdown)
                [_usage_row(total_units=600.0, quota_snap=100.0)],
                # "2026-03"-scoped call (quota only)
                [_usage_row(total_units=80.0, quota_snap=100.0)],
            ]),
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row(spent=Decimal("300"))),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-03", None, None, auth_db=None)

        item = result.data[0]
        assert item.spend == 300.0  # all-time, unaffected by the given month
        assert item.usage.consumed == 80.0  # scoped to the given month, not all-time

        assert repo.get_tenant_tier_usage_breakdown.call_count == 2
        first_call, second_call = repo.get_tenant_tier_usage_breakdown.call_args_list
        assert first_call.args[0] is None
        assert second_call.args[0] == "2026-03"

    @pytest.mark.asyncio
    async def test_model_task_type_filter_narrows_usage_but_not_spend(self):
        """model_task_type only affects the flat `usage` quota-bar fields — spend
        (real, tenant-total, from get_tenant_budgets) and tierBreakdown (unit-based,
        from usage_rows) always reflect the tenant's full period totals."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(task_type="llm", total_units=100.0, quota_snap=200.0),
                _usage_row(task_type="asr", total_units=50.0, quota_snap=None),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row(spent=Decimal("50"))),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, _TYPE_IDS["asr"], auth_db=None)

        item = result.data[0]
        assert item.spend == 50.0  # real tenant-total, unaffected by the filter
        assert len(item.tierBreakdown[0].taskTypes) == 2  # both task types still present
        assert item.usage.consumed == 50.0  # narrowed to "asr" only
        assert item.usage.quotaLimit is None

    @pytest.mark.asyncio
    async def test_hierarchical_build_only_runs_for_paginated_page(self):
        """Sorting/pagination must happen before the expensive per-tenant build — so
        tier_first_seen and tenant-name resolution should only be called for the
        tenants on the requested page, not every matching tenant. get_tenant_budgets
        is the one exception (see get_tenant_list's own docstring): sorting is now by
        real spend, which requires budgets for the FULL matching tenant_ids, not just
        the page — a real cost, not a free pre-aggregate, but unavoidable for
        correct sorting."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[
                _tier_row(tenant_id="t1"),
                _tier_row(tenant_id="t2"),
                _tier_row(tenant_id="t3"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1"),
                _usage_row(tenant_id="t2"),
                _usage_row(tenant_id="t3"),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(
                _budget_row(tenant_id="t1", spent=Decimal("10")),
                _budget_row(tenant_id="t2", spent=Decimal("90")),
                _budget_row(tenant_id="t3", spent=Decimal("50")),
            ),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list(
            "2026-06", None, None, auth_db=None, sort_order="desc", limit=1, offset=0
        )

        assert [item.tenantId for item in result.data] == ["t2"]
        assert result.total == 3
        # only the top-1 tenant (t2) should have its tier_first_seen resolved
        repo.get_tier_first_seen.assert_called_once_with(["t2"])
        # budgets fetched once, for the full matching set (needed to sort correctly)
        repo.get_tenant_budgets.assert_called_once_with("2026-06", ["t1", "t2", "t3"], None)

    @pytest.mark.asyncio
    async def test_tied_spend_breaks_deterministically_by_tenant_id(self):
        """Tenants tied on spend (e.g. all at 0) must sort by tenant_id as a tiebreaker,
        so identical input always produces identical page contents — otherwise two
        sequential paginated calls could duplicate or drop a tied tenant across pages."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[
                _tier_row(tenant_id="t3"),
                _tier_row(tenant_id="t1"),
                _tier_row(tenant_id="t2"),
            ],
            get_tenant_tier_usage_breakdown=[],  # every tenant ties at spend=0
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)

        result_a = await svc.get_tenant_list("2026-06", None, None, auth_db=None, limit=2, offset=0)
        result_b = await svc.get_tenant_list("2026-06", None, None, auth_db=None, limit=2, offset=0)

        assert [i.tenantId for i in result_a.data] == [i.tenantId for i in result_b.data]

    @pytest.mark.asyncio
    async def test_sort_order_desc_by_spend(self):
        """Regression: without real per-tenant spend in the budgets fixture, both
        tenants would tie at spent=0 and this would pass purely off the tenant_id
        tiebreak, not real sorting — spent is set here so desc genuinely depends on
        it (t1 < t2 alphabetically, but t1 has the HIGHER spend, so passing this
        proves sorting is by spend, not accidentally by tenant_id)."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[
                _tier_row(tenant_id="t1"),
                _tier_row(tenant_id="t2"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1"),
                _usage_row(tenant_id="t2"),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(
                _budget_row(tenant_id="t1", spent=Decimal("90")),
                _budget_row(tenant_id="t2", spent=Decimal("10")),
            ),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None, sort_order="desc")

        assert [item.tenantId for item in result.data] == ["t1", "t2"]

    @pytest.mark.asyncio
    async def test_sort_order_asc_by_spend(self):
        """Same anti-tiebreak-false-positive reasoning as test_sort_order_desc_by_spend."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[
                _tier_row(tenant_id="t1"),
                _tier_row(tenant_id="t2"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1"),
                _usage_row(tenant_id="t2"),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(
                _budget_row(tenant_id="t1", spent=Decimal("90")),
                _budget_row(tenant_id="t2", spent=Decimal("10")),
            ),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None, sort_order="asc")

        assert [item.tenantId for item in result.data] == ["t2", "t1"]

    @pytest.mark.asyncio
    async def test_no_assignments_returns_empty_response(self):
        repo = _make_repo(get_tenants_with_usage_tier=[])
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        assert result.data == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_pagination_slices_page_but_total_is_full_count(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[
                _tier_row(tenant_id="t1"),
                _tier_row(tenant_id="t2"),
                _tier_row(tenant_id="t3"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1"),
                _usage_row(tenant_id="t2"),
                _usage_row(tenant_id="t3"),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(
                _budget_row(tenant_id="t1", spent=Decimal("10")),
                _budget_row(tenant_id="t2", spent=Decimal("90")),
                _budget_row(tenant_id="t3", spent=Decimal("50")),
            ),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list(
            "2026-06", None, None, auth_db=None, sort_order="desc", limit=1, offset=1
        )

        # sorted desc by spend: t2(90), t3(50), t1(10) -> offset=1, limit=1 -> just t3
        assert [item.tenantId for item in result.data] == ["t3"]
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_offset_past_end_returns_empty_page_with_full_total(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None, offset=10, limit=10)

        assert result.data == []
        assert result.total == 1


# ── get_tenant_detail ─────────────────────────────────────────────────────────

class TestGetTenantDetail:
    @pytest.mark.asyncio
    async def test_spend_reflects_real_budget_usage_not_hardcoded_zero(self):
        """Regression: same bug as get_tenant_list's — spend/budget.spent/
        budget.percentageUsed must reflect the real sum of budget_usage.
        api_key_budget_used (get_tenant_budgets), not the removed cost_accum
        placeholder that made these always 0."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row(
                budget_limit=Decimal("10000"), spent=Decimal("4321"),
            )),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.spend == 4321.0
        assert result.budget.spent == 4321.0
        assert result.budget.percentageUsed == 43.2  # 4321 / 10000 * 100, rounded

    @pytest.mark.asyncio
    async def test_returns_zero_value_item_when_no_assignment(self):
        # No usage this period is a valid tenant state (not an error) — the API
        # should return a zero-value item, not a 404.
        repo = _make_repo(get_tenants_with_usage_tier=[])
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.tenantId == "t1"
        assert result.tier == "Unassigned"
        assert result.tierId == "unassigned"
        assert result.spend == 0.0
        assert result.budget.limit == 0.0
        assert result.budget.remaining == 0.0
        assert result.usage.taskTypeCount == 0
        assert result.tierBreakdown == []

    @pytest.mark.asyncio
    async def test_zero_usage_shows_current_tier_assignment_when_one_exists(self):
        """A tenant with no usage yet this billing_month (e.g. just onboarded) but a
        live ppu_tenant_tier_assignments row must show that tier, not "Unassigned" —
        there's no usage to derive a tier from, but the tenant does have one."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[],
            get_tenant_budgets=_budgets(_budget_row(tenant_id="t1", tier_id="2")),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.tier == "Enterprise"
        assert result.tierId == "2"
        # zero-usage-this-period otherwise (no tierBreakdown/usage to build), but
        # spend is real and always all-time — it reflects the budget row's real
        # spend (default 300 from _budget_row), not 0, since spend is independent
        # of whether there are ppu_quota_usage rows in scope this billing_month.
        assert result.spend == 300.0
        assert result.usage.taskTypeCount == 0
        assert result.tierBreakdown == []

    @pytest.mark.asyncio
    async def test_zero_usage_with_live_budget_shows_real_allocated_and_remaining(self):
        """A tenant with a live assignment but no usage yet this period has a real
        allocated/remaining budget — budget.limit/remaining must not collapse to 0
        just because there's no usage to build a hierarchical item from (previously
        it did, even with a real budget_limit/available_balance on file)."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[],
            get_tenant_budgets=_budgets(
                _budget_row(tenant_id="t1", budget_limit=Decimal("1000"), available_balance=Decimal("700"))
            ),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.budget.limit == 1000.0
        assert result.budget.remaining == 700.0

    @pytest.mark.asyncio
    async def test_zero_usage_this_month_still_shows_real_lifetime_spend(self):
        """Regression (self-review catch): a tenant with zero ppu_quota_usage rows
        for THIS billing_month can still have real lifetime spend from other
        months — budget_usage has no per-month dimension, so spend must not
        collapse to 0 in this branch just because there's nothing to build a
        hierarchical item from here either. E.g. a tenant spent 5000 in June but
        billing_period=2026-01 (no activity that month) must still show spend=5000,
        not 0 — spend is always all-time (see get_tenant_list's docstring)."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[],
            get_tenant_budgets=_budgets(_budget_row(
                tenant_id="t1", budget_limit=Decimal("10000"), spent=Decimal("5000"),
            )),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-01", auth_db=None)

        assert result.spend == 5000.0
        assert result.budget.spent == 5000.0
        assert result.budget.percentageUsed == 50.0

    @pytest.mark.asyncio
    async def test_returns_zero_value_item_when_tenant_exists_but_unassigned(self):
        # auth_db confirms the tenant is real (just has no usage this period) — still
        # the zero-value empty state, not a 404.
        repo = _make_repo(get_tenants_with_usage_tier=[])
        svc = UsageService(repo)
        auth_db = MagicMock()
        auth_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(3, "No Tier Test Org")]))
        )

        result = await svc.get_tenant_detail("3", "2026-06", auth_db=auth_db)

        assert result.tenantId == "3"
        assert result.tenantName == "No Tier Test Org"
        assert result.tier == "Unassigned"

    @pytest.mark.asyncio
    async def test_raises_when_tenant_does_not_exist(self):
        # An empty `assignments` list also happens for a tenant_id that was never
        # real (typo, deleted tenant) — auth_db resolving no matching row is how we
        # tell that apart from the legitimate unassigned case, and it must still 404.
        from app.core.exceptions import EntityNotFoundError

        repo = _make_repo(get_tenants_with_usage_tier=[])
        svc = UsageService(repo)
        auth_db = MagicMock()
        auth_db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        with pytest.raises(EntityNotFoundError):
            await svc.get_tenant_detail("999", "2026-06", auth_db=auth_db)

    @pytest.mark.asyncio
    async def test_single_tenant_hierarchical_shape(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row()),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.tenantId == "t1"
        assert result.spend == 300.0
        assert result.budget.limit == 1000.0
        assert result.budget.remaining == 700.0
        assert result.usage.consumed == 100.0
        assert result.usage.quotaLimit == 200.0
        assert len(result.tierBreakdown) == 1

    @pytest.mark.asyncio
    async def test_budget_effective_from_and_to_included_in_response(self):
        """/usage-tenant's budget block must surface the tenant's configured budget
        window (tenants.budget_effective_from/to) — read through get_tenant_budgets,
        merged onto the assignment in _merge_tier_and_budget, and passed separately
        into _to_tenant_usage_detail since TenantHierarchicalItem's own budget field
        never carries it (see TenantBudgetDetail)."""
        effective_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        effective_to = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row(
                budget_effective_from=effective_from, budget_effective_to=effective_to,
            )),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.budget.budgetEffectiveFrom == effective_from
        assert result.budget.budgetEffectiveTo == effective_to

    @pytest.mark.asyncio
    async def test_budget_effective_from_and_to_null_when_not_configured(self):
        """A tenant with a real budget but no configured window (both columns
        nullable — set only at tenant creation) must show null, not crash or
        default to some other value."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row()),  # defaults both to None
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.budget.budgetEffectiveFrom is None
        assert result.budget.budgetEffectiveTo is None

    @pytest.mark.asyncio
    async def test_budget_effective_from_and_to_null_for_zero_usage_tenant(self):
        """Same fields, same source, but through get_tenant_detail's separate
        zero-usage early-return branch (no ppu_quota_usage rows this period) —
        must also surface the tenant's configured budget window, not just the
        normal (has-usage) path."""
        effective_from = datetime(2026, 3, 1, tzinfo=timezone.utc)
        effective_to = datetime(2026, 9, 30, tzinfo=timezone.utc)
        repo = _make_repo(
            get_tenants_with_usage_tier=[],
            get_tenant_budgets=_budgets(_budget_row(
                budget_effective_from=effective_from, budget_effective_to=effective_to,
            )),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.budget.budgetEffectiveFrom == effective_from
        assert result.budget.budgetEffectiveTo == effective_to

    @pytest.mark.asyncio
    async def test_omitted_billing_month_keeps_quota_current_month_but_spend_all_time(self, monkeypatch):
        """Regression: same bug as get_tenant_list's — billing_month=None ("all-time")
        must widen spend/budget to a lifetime total, but quota (consumed/quotaLimit/
        remaining/percentage) resets monthly and must stay scoped to the current
        month, not summed across every month like spend."""
        _freeze_now(monkeypatch, datetime(2026, 6, 15, tzinfo=timezone.utc))
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=_Seq([
                # all-time call (billing_month=None): 6 months of usage summed
                [_usage_row(total_units=600.0, total_cost=Decimal("300"), quota_snap=100.0)],
                # current-month-only call (billing_month="2026-06"): just this month
                [_usage_row(total_units=100.0, total_cost=Decimal("50"), quota_snap=100.0)],
            ]),
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(_budget_row(budget_limit=Decimal("10000"), available_balance=Decimal("9700"))),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", None, auth_db=None)

        assert result.spend == 300.0  # lifetime total
        assert result.usage.consumed == 100.0  # current month only, not the 600 lifetime total
        assert result.usage.quotaLimit == 100.0
        assert result.usage.percentage == 100.0  # not 600.0

        assert repo.get_tenant_tier_usage_breakdown.call_count == 2
        first_call, second_call = repo.get_tenant_tier_usage_breakdown.call_args_list
        assert first_call.args[0] is None
        assert second_call.args[0] == "2026-06"

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_row_shows_zero_budget(self):
        """A tenant with usage this month but no ppu_tenant_tier_assignments row
        covering this period's end (e.g. the exact off-by-a-day case that motivated
        this redesign) must still show usage/tier data, just with budget=0."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.tier == "Pro"
        # No budget row on file means no real spend data either (spend is sourced
        # from budget_usage via get_tenant_budgets) — 0, same "unknown" convention
        # as budget.limit/remaining (see _resolve_spent).
        assert result.spend == 0.0
        assert result.budget.limit == 0.0
        assert result.budget.remaining == 0.0

    @pytest.mark.asyncio
    async def test_multi_task_type_breakdown_omits_spend_and_percentage(self):
        """/usage-tenant's tierBreakdown taskTypes entries drop spend/percentage —
        unlike /usage-tenants (the list endpoint), which still shows both per task
        type (see TestGetTenantList's percentage/spend assertions)."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(task_type="llm", total_cost=Decimal("75")),
                _usage_row(task_type="asr", total_cost=Decimal("25")),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        task_types = result.tierBreakdown[0].taskTypes
        assert len(task_types) == 2
        assert not hasattr(task_types[0], "percentage")
        assert not hasattr(task_types[0], "spend")
        # multiple distinct task types -> nothing to disambiguate, usage stays unset —
        # except `unit`, which falls back to "Units" (matching the old flat
        # TenantUsageItem.quotaUnit contract, which was never null).
        assert result.usage.taskTypeCount == 2
        assert result.usage.consumed is None
        assert result.usage.unit == "Units"


# ── _resolve_tenant_names ─────────────────────────────────────────────────────

class TestResolveTenantNames:
    @pytest.mark.asyncio
    async def test_logs_warning_on_auth_db_failure(self, caplog):
        """Auth DB exception must be logged, not silently swallowed."""
        import logging
        from app.services.pay_per_use.usage_service import _resolve_tenant_names

        broken_db = MagicMock()
        broken_db.execute = AsyncMock(side_effect=Exception("connection refused"))
        broken_db.rollback = AsyncMock()

        with caplog.at_level(logging.WARNING, logger="app.services.pay_per_use.usage_service"):
            result = await _resolve_tenant_names(["1", "2"], broken_db)

        assert result == {}
        assert any("connection refused" in r.message for r in caplog.records)
        broken_db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure_does_not_poison_session_for_the_next_auth_db_query(self):
        """Regression: a bare AsyncMock lets a second .execute() succeed even
        after the first one raised, which hides the real bug — a real
        Postgres/SQLAlchemy AsyncSession aborts its transaction on a raising
        query and rejects every further statement (PendingRollbackError)
        until .rollback() runs. get_tenant_list/get_tenant_detail always
        reuse this same auth_db for self._repo.get_tenant_budgets right
        after this call, so without a rollback here, one flaky name lookup
        would 500 an otherwise-healthy budget lookup too."""
        from app.services.pay_per_use.usage_service import _resolve_tenant_names

        class _PoisonableAuthDB:
            def __init__(self) -> None:
                self._call_count = 0
                self._poisoned = False
                self.rollback = AsyncMock(side_effect=self._clear_poison)

            def _clear_poison(self) -> None:
                self._poisoned = False

            async def execute(self, *args, **kwargs):
                self._call_count += 1
                if self._poisoned:
                    raise RuntimeError(
                        "This Session's transaction has been rolled back due to a "
                        "previous exception during flush."  # PendingRollbackError
                    )
                if self._call_count == 1:
                    self._poisoned = True
                    raise RuntimeError("connection reset by peer")
                result = MagicMock()
                result.all.return_value = []
                return result

        db = _PoisonableAuthDB()

        org_map = await _resolve_tenant_names(["1", "2"], db)

        assert org_map == {}
        db.rollback.assert_awaited_once()
        # The exact bug scenario: a second, unrelated query on the same
        # session (standing in for get_tenant_budgets) must succeed, not
        # inherit the first query's failure as a PendingRollbackError.
        result = await db.execute("SELECT 1")
        assert result.all() == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_auth_db(self):
        from app.services.pay_per_use.usage_service import _resolve_tenant_names
        result = await _resolve_tenant_names(["1"], auth_db=None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_resolves_integer_tenant_ids(self):
        """Numeric string IDs must reach the DB and return the org name mapping."""
        from app.services.pay_per_use.usage_service import _resolve_tenant_names

        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                all=MagicMock(return_value=[(1, "Acme Corp"), (42, "Beta Labs")])
            )
        )

        result = await _resolve_tenant_names(["1", "42"], auth_db=db)

        db.execute.assert_called_once()
        assert result == {"1": "Acme Corp", "42": "Beta Labs"}

    @pytest.mark.asyncio
    async def test_skips_db_when_no_valid_integer_ids(self):
        """Non-integer IDs are silently skipped — tenant_id is INTEGER in the PPU schema,
        so a string like 'abc' can never match a row and the DB round-trip is avoided."""
        from app.services.pay_per_use.usage_service import _resolve_tenant_names

        db = MagicMock()
        result = await _resolve_tenant_names(["abc", "uuid-xyz"], auth_db=db)

        assert result == {}
        db.execute.assert_not_called()
