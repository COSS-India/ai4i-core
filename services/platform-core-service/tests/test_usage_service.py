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
from app.core.exceptions import EntityNotFoundError
from app.services.pay_per_use.usage_service import UsageService
from app.utils.usage_period import resolve_period


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


# Before every period the tests use: the usage data covers them whole.
_DATA_SINCE = datetime(2020, 1, 1, tzinfo=timezone.utc)


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

    get_usage_data_from defaults to a date before every period (the usage
    data covers it whole); get_estimated_until to None (nothing estimated).
    """
    repo = MagicMock()
    method_returns.setdefault("get_tier_names", {"1": "Pro", "2": "Enterprise"})
    method_returns.setdefault("get_tenant_budgets", {})
    method_returns.setdefault("get_budgeted_tenant_budgets", {})
    method_returns.setdefault("get_tenants_with_usage_tier", [])
    method_returns.setdefault("get_tenant_tier_usage_breakdown", [])
    method_returns.setdefault("get_usage_data_from", _DATA_SINCE)
    method_returns.setdefault("get_estimated_until", None)
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

_AUTH_DB = object()   # stands in for the auth session; the repo is mocked


class TestSummaryBudget:
    """The budget block: all-time, every institution with a budget on file —
    picked from tenants, not quota rows, and never scoped by billing_period."""

    @pytest.mark.asyncio
    async def test_totals_across_every_budgeted_institution(self):
        repo = _make_repo(
            get_budgeted_tenant_budgets=_budgets(
                _budget_row(tenant_id="t1", budget_limit=Decimal("1000"),
                            available_balance=Decimal("700"), spent=Decimal("300")),
                _budget_row(tenant_id="t2", budget_limit=Decimal("500"),
                            available_balance=Decimal("200"), spent=Decimal("300")),
            ),
        )
        budget = (await UsageService(repo).get_summary("2026-06", auth_db=_AUTH_DB)).budget

        assert budget.basis == "all_time"
        assert (budget.institutions, budget.allocated, budget.spent, budget.remaining) == (2, 1500, 600, 900)
        repo.get_budgeted_tenant_budgets.assert_awaited_once_with(_AUTH_DB, None)
        repo.get_tenant_budgets.assert_not_called()   # one read of tenants, not two

    @pytest.mark.asyncio
    async def test_institution_without_quota_rows_still_counts(self):
        """Untiered keys: spend in budget_usage, no ppu_quota_usage rows. It used
        to drop out of the summary; the budget block doesn't read quota rows."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[],          # no quota rows at all
            get_tenant_tier_usage_breakdown=[],
            get_budgeted_tenant_budgets=_budgets(_budget_row(budget_limit=Decimal("10"), spent=Decimal("50"))),
        )
        result = await UsageService(repo).get_summary("2026-06", auth_db=_AUTH_DB)

        assert (result.budget.spent, result.budget.exceededTenants) == (50, 1)
        assert result.quota.activeTenants == 0

    @pytest.mark.asyncio
    async def test_billing_period_does_not_change_the_budget(self):
        repo = _make_repo(
            get_budgeted_tenant_budgets=_budgets(_budget_row(spent=Decimal("50"))),
        )
        svc = UsageService(repo)
        june = await svc.get_summary("2026-06", auth_db=_AUTH_DB)
        all_months = await svc.get_summary(None, auth_db=_AUTH_DB)

        assert june.budget == all_months.budget
        for call in repo.get_budgeted_tenant_budgets.await_args_list:
            assert call.args == (_AUTH_DB, None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("limit", "spent", "exceeded"),
        [("100", "100", 1),     # reached: the >= billing applies per key, per institution
         ("100", "150", 1),     # over
         ("100", "99.99", 0),   # just under
         ("0", "0", 0)],        # nothing allocated, nothing to exhaust
    )
    async def test_exceeded_means_spend_reached_the_budget(self, limit, spent, exceeded):
        repo = _make_repo(
            get_budgeted_tenant_budgets=_budgets(_budget_row(budget_limit=Decimal(limit), spent=Decimal(spent))),
        )
        result = await UsageService(repo).get_summary("2026-06", auth_db=_AUTH_DB)
        assert result.budget.exceededTenants == exceeded

    @pytest.mark.asyncio
    async def test_tier_filter_is_the_current_tier_and_says_so(self):
        """The two blocks filter on different tiers: budget on the current tier
        (tenants.tier_id), quota on the most recent tier in the quota rows. An
        institution whose tier was removed is out of budget but can be in quota,
        so each block names the rule it used."""
        repo = _make_repo(
            get_budgeted_tenant_budgets={},                  # tenants.tier_id is NULL now
            get_tenants_with_usage_tier=[_tier_row()],       # still on tier "1" in its quota rows
            get_tenant_tier_usage_breakdown=[_usage_row()],
        )
        result = await UsageService(repo).get_summary("2026-06", tier_id="1", auth_db=_AUTH_DB)

        repo.get_budgeted_tenant_budgets.assert_awaited_once_with(_AUTH_DB, "1")
        assert (result.budget.institutions, result.budget.tierFilter) == (0, "current_tier")
        assert (result.quota.activeTenants, result.quota.tierFilter) == (1, "most_recent_quota_tier")

    @pytest.mark.asyncio
    async def test_no_tier_filter_no_tier_rule(self):
        result = await UsageService(_make_repo()).get_summary("2026-06", auth_db=_AUTH_DB)
        assert (result.budget.tierFilter, result.quota.tierFilter) == (None, None)

    @pytest.mark.asyncio
    async def test_only_the_two_blocks_and_currency(self):
        """Spend is lifetime only: no month-scoped money and no month-over-month
        change anywhere in the response."""
        result = await UsageService(_make_repo()).get_summary("2026-06", auth_db=_AUTH_DB)

        assert set(result.model_dump()) == {"currency", "budget", "quota"}
        assert "spendChangePercent" not in str(result.model_dump())


class TestSummaryQuota:
    """The quota block: one billing month (all months when omitted), across
    institutions with ppu_quota_usage rows in scope."""

    @pytest.mark.asyncio
    async def test_consumption_and_active_tenants(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
        )
        quota = (await UsageService(repo).get_summary("2026-06")).quota

        assert (quota.basis, quota.billingMonth, quota.activeTenants) == ("billing_month", "2026-06", 1)
        assert quota.byTaskType[0].consumption == 100.0

    @pytest.mark.asyncio
    async def test_items_carry_no_money(self):
        """ppu_quota_usage has no per-task-type money column."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row(task_type="llm"), _usage_row(task_type="asr")],
        )
        quota = (await UsageService(repo).get_summary("2026-06")).quota

        assert len(quota.byTaskType) == 2
        assert not hasattr(quota.byTaskType[0], "spend")
        assert not hasattr(quota.byTaskType[0], "percentage")

    @pytest.mark.asyncio
    async def test_omitted_billing_period_is_all_months(self):
        """None reaches the repository (no month filter), and billingMonth is
        null — not a sentinel string — so echoing it back as billing_period works
        (the route's YYYY-MM pattern would reject "lifetime")."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
        )
        quota = (await UsageService(repo).get_summary(None)).quota

        assert (quota.basis, quota.billingMonth) == ("all_time", None)
        assert not re.compile(r"^\d{4}-(0[1-9]|1[0-2])$").match("lifetime")
        repo.get_tenants_with_usage_tier.assert_called_once_with(None, None, task_type_ids=None)
        repo.get_tenant_tier_usage_breakdown.assert_called_once_with(None, ["t1"], task_type_ids=None)

    @pytest.mark.asyncio
    async def test_tier_and_task_types_scope_the_quota_rows(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
        )
        await UsageService(repo).get_summary("2026-06", tier_id="1", task_type_ids=[2])

        repo.get_tenants_with_usage_tier.assert_called_once_with("2026-06", "1", task_type_ids=[2])

    @pytest.mark.asyncio
    async def test_allocated_summed_across_tenants_current_tier(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row(tenant_id="t1"), _tier_row(tenant_id="t2", tier_id="2")],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", tier_id="1", total_units=100.0, quota_snap=200.0),
                _usage_row(tenant_id="t2", tier_id="2", total_units=50.0, quota_snap=300.0),
            ],
        )
        quota = (await UsageService(repo).get_summary("2026-06")).quota

        llm = next(i for i in quota.byTaskType if i.modelTaskType == "llm")
        assert (llm.consumption, llm.allocated) == (150.0, 500.0)

    @pytest.mark.asyncio
    async def test_allocated_null_when_no_quota_snapshot(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row(quota_snap=None)],
        )
        quota = (await UsageService(repo).get_summary("2026-06")).quota
        assert quota.byTaskType[0].allocated is None

    @pytest.mark.asyncio
    async def test_allocated_per_task_type_in_its_own_unit(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(task_type="llm", total_units=100.0, quota_snap=200.0),
                _usage_row(task_type="asr", total_units=10.0, quota_snap=50.0),
            ],
        )
        by_type = {i.modelTaskType: i for i in (await UsageService(repo).get_summary("2026-06")).quota.byTaskType}
        assert (by_type["llm"].allocated, by_type["asr"].allocated) == (200.0, 50.0)

    @pytest.mark.asyncio
    async def test_allocated_excludes_quota_from_non_current_tier(self):
        """A quota grant resets on reassignment: only the current tier's row
        counts toward allocated; consumption sums across every tier used."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row(tier_id="2")],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tier_id="1", total_units=100.0, quota_snap=500.0),
                _usage_row(tier_id="2", total_units=50.0, quota_snap=100.0),
            ],
        )
        item = (await UsageService(repo).get_summary("2026-06")).quota.byTaskType[0]
        assert (item.consumption, item.allocated) == (150.0, 100.0)


# ── get_tenant_list ───────────────────────────────────────────────────────────

# ── get_tenant_list / get_tenant_detail (period figures) ─────────────────────

_TODAY = resolve_period("today", None, None, now=datetime(2026, 10, 9, 8, 50, tzinfo=timezone.utc))
_YESTERDAY = resolve_period("yesterday", None, None, now=datetime(2026, 10, 9, 8, 50, tzinfo=timezone.utc))


def _period_row(**kwargs):
    """One row as get_period_usage projects it (usage_events / daily_usage,
    grouped by tenant, tier and task type). tenant_id is the integer column."""
    task_type = kwargs.pop("task_type", "nmt")
    defaults = dict(
        tenant_id=1, tier_id="1",
        inference_type_id=_TYPE_IDS.get(task_type), task_type=task_type,
        task_type_unit=_TYPE_UNITS.get(task_type),
        total_units=Decimal("100"), cached_input_units=Decimal("0"), output_units=Decimal("0"),
        input_units_cost=Decimal("1.5"), cached_input_units_cost=Decimal("0"),
        output_units_cost=Decimal("0"), cost=Decimal("1.5"),
        first_seen=datetime(2026, 10, 9, 1, tzinfo=timezone.utc),
        last_seen=datetime(2026, 10, 9, 2, tzinfo=timezone.utc),
    )
    return _row(**{**defaults, **kwargs})


def _llm_row(**kwargs):
    """The reference UI's LLM row: 3,500 input + 500 cached + 200 output tokens
    = 4,200; ₹0.35 + ₹0.02048 + ₹0.05 = ₹0.42048."""
    defaults = dict(
        task_type="llm", total_units=Decimal("4200"), cached_input_units=Decimal("500"),
        output_units=Decimal("200"), input_units_cost=Decimal("0.35"),
        cached_input_units_cost=Decimal("0.02048"), output_units_cost=Decimal("0.05"),
        cost=Decimal("0.42048"),
    )
    return _period_row(**{**defaults, **kwargs})


def _quota_row(**kwargs):
    """One current-month row as get_tenant_tier_usage_breakdown projects it."""
    return _usage_row(**{"tenant_id": "1", **kwargs})


@pytest.mark.asyncio
class TestGetTenantList:
    async def test_period_spend_next_to_all_time_budget(self, monkeypatch):
        _freeze_now(monkeypatch, datetime(2026, 10, 9, tzinfo=timezone.utc))
        repo = _make_repo(
            get_period_usage=[_period_row()],
            get_tenant_tier_usage_breakdown=[],
            get_tenant_budgets=_budgets(_budget_row(tenant_id="1")),
        )
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, auth_db=None)

        item = result.data[0]
        assert result.period.key == "today"
        assert item.tenantId == "1"
        assert item.periodSpend == 1.5
        assert (item.budget.limit, item.budget.spent, item.budget.remaining) == (1000, 300, 700)
        assert item.budget.percentageUsed == 30.0
        assert item.budget.basis == "all_time"   # labelled: not scoped by the period
        assert "spend" not in item.model_dump()

    async def test_reads_the_period_from_the_repository(self):
        repo = _make_repo(get_period_usage=[], get_tenant_tier_usage_breakdown=[])
        await UsageService(repo).get_tenant_list(_YESTERDAY, None, None, None, task_type_ids=[3])
        repo.get_period_usage.assert_awaited_once_with(_YESTERDAY, task_type_ids=[3])

    async def test_no_usage_in_the_period_is_an_empty_page(self):
        repo = _make_repo(get_period_usage=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        assert (result.data, result.total) == ([], 0)
        repo.get_tenant_budgets.assert_not_called()

    async def test_period_reports_how_much_the_usage_data_covers(self):
        repo = _make_repo(get_period_usage=[], get_usage_data_from=None)
        result = await UsageService(repo).get_tenant_list(_YESTERDAY, None, None, None)
        assert (result.period.dataFrom, result.period.partial) == (None, True)

        repo = _make_repo(get_period_usage=[])
        result = await UsageService(repo).get_tenant_list(_YESTERDAY, None, None, None)
        assert (result.period.dataFrom, result.period.partial) == ("2026-10-08T00:00:00+05:30", False)

    async def test_sorted_by_period_spend_with_tenant_id_tie_break(self):
        rows = [
            _period_row(tenant_id=1, cost=Decimal("5")),
            _period_row(tenant_id=2, cost=Decimal("9")),
            _period_row(tenant_id=3, cost=Decimal("5")),
        ]
        repo = _make_repo(get_period_usage=rows, get_tenant_tier_usage_breakdown=[])
        desc = await UsageService(repo).get_tenant_list(_TODAY, None, None, None, sort_order="desc")
        asc = await UsageService(repo).get_tenant_list(_TODAY, None, None, None, sort_order="asc")
        assert [i.tenantId for i in desc.data] == ["2", "3", "1"]
        assert [i.tenantId for i in asc.data] == ["1", "3", "2"]

    async def test_pagination_builds_only_the_page(self):
        rows = [_period_row(tenant_id=t, cost=Decimal(t)) for t in (1, 2, 3, 4)]
        repo = _make_repo(get_period_usage=rows, get_tenant_tier_usage_breakdown=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None, limit=2, offset=1)
        assert result.total == 4
        assert [i.tenantId for i in result.data] == ["3", "2"]
        assert repo.get_tenant_budgets.call_args.args[0] == ["3", "2"]

    async def test_tier_filter_uses_the_most_recent_tier_in_the_period(self):
        tier_a, tier_b = "6f1c2a9e-4b1d-4f0e-9a51-3c7d2e8b1f04", "0b5e0d2a-9c41-4a7e-8e0f-2d6c4f1a3b77"
        rows = [
            _period_row(tenant_id=1, tier_id=tier_a, last_seen=datetime(2026, 10, 9, 1, tzinfo=timezone.utc)),
            _period_row(tenant_id=1, tier_id=tier_b, task_type="tts",
                        last_seen=datetime(2026, 10, 9, 5, tzinfo=timezone.utc)),
            _period_row(tenant_id=2, tier_id=tier_a),
        ]
        repo = _make_repo(get_period_usage=rows, get_tenant_tier_usage_breakdown=[],
                          get_tier_names={tier_a: "Gold", tier_b: "Silver"})
        result = await UsageService(repo).get_tenant_list(_TODAY, tier_a.upper(), None, None)
        assert [i.tenantId for i in result.data] == ["2"]

        both = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        tenant_1 = next(i for i in both.data if i.tenantId == "1")
        assert (tenant_1.tier, tenant_1.tierId) == ("Silver", tier_b)

    async def test_model_task_type_keeps_institutions_that_used_it(self):
        rows = [_period_row(tenant_id=1, task_type="nmt"), _llm_row(tenant_id=2)]
        repo = _make_repo(get_period_usage=rows, get_tenant_tier_usage_breakdown=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, _TYPE_IDS["llm"], None)
        assert [i.tenantId for i in result.data] == ["2"]

    async def test_llm_cost_breakdown_matches_the_reference_ui(self):
        repo = _make_repo(get_period_usage=[_llm_row()], get_tenant_tier_usage_breakdown=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)

        usage = result.data[0].tierBreakdown[0].taskTypes[0].periodUsage
        assert (usage.units, usage.cost) == (4200, 0.42)
        assert [b.model_dump() for b in usage.breakdown] == [
            {"key": "input", "label": "Input tokens", "units": 3500, "cost": 0.35, "costShare": 83.24},
            {"key": "cached_input", "label": "Cached input tokens", "units": 500, "cost": 0.02, "costShare": 4.87},
            {"key": "output", "label": "Output tokens", "units": 200, "cost": 0.05, "costShare": 11.89},
        ]
        assert sum(b.units for b in usage.breakdown) == usage.units

    async def test_llm_cost_parts_add_up_to_the_cost(self):
        """Rounded independently, three parts of 0.335 would show 0.34 each
        (1.02) against a cost of 1.01; the residual goes to the largest part."""
        row = _llm_row(input_units_cost=Decimal("0.335"), cached_input_units_cost=Decimal("0.335"),
                       output_units_cost=Decimal("0.335"), cost=Decimal("1.005"))
        repo = _make_repo(get_period_usage=[row], get_tenant_tier_usage_breakdown=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        usage = result.data[0].tierBreakdown[0].taskTypes[0].periodUsage
        assert usage.cost == 1.01
        assert round(sum(b.cost for b in usage.breakdown), 2) == usage.cost
        assert round(sum(b.costShare for b in usage.breakdown), 2) == 100.0

    async def test_zero_cached_input_is_omitted(self):
        row = _llm_row(cached_input_units=Decimal("0"), cached_input_units_cost=Decimal("0"),
                       cost=Decimal("0.40"))
        repo = _make_repo(get_period_usage=[row], get_tenant_tier_usage_breakdown=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        breakdown = result.data[0].tierBreakdown[0].taskTypes[0].periodUsage.breakdown
        assert [b.key for b in breakdown] == ["input", "output"]

    async def test_non_llm_rows_have_no_breakdown(self):
        repo = _make_repo(get_period_usage=[_period_row()], get_tenant_tier_usage_breakdown=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        assert result.data[0].tierBreakdown[0].taskTypes[0].periodUsage.breakdown is None

    async def test_quota_is_the_current_billing_month(self, monkeypatch):
        _freeze_now(monkeypatch, datetime(2026, 10, 9, tzinfo=timezone.utc))
        repo = _make_repo(
            get_period_usage=[_llm_row()],
            get_tenant_tier_usage_breakdown=[_quota_row(task_type="llm", total_units=31200.0, quota_snap=100_000_000.0)],
        )
        result = await UsageService(repo).get_tenant_list(_YESTERDAY, None, None, None)

        assert repo.get_tenant_tier_usage_breakdown.call_args.args[0] == "2026-10"
        quota = result.data[0].tierBreakdown[0].taskTypes[0].quota
        assert quota.model_dump() == {
            "billingMonth": "2026-10", "limit": 100_000_000, "used": 31200,
            "remaining": 99_968_800, "percentageUsed": 0.03,
        }

    async def test_over_quota_remaining_is_negative(self, monkeypatch):
        _freeze_now(monkeypatch, datetime(2026, 10, 9, tzinfo=timezone.utc))
        repo = _make_repo(
            get_period_usage=[_period_row()],
            get_tenant_tier_usage_breakdown=[_quota_row(task_type="nmt", total_units=250.0, quota_snap=200.0)],
        )
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        quota = result.data[0].tierBreakdown[0].taskTypes[0].quota
        assert (quota.remaining, quota.percentageUsed) == (-50, 125.0)

    async def test_zero_quota_with_usage_is_fully_exhausted(self, monkeypatch):
        _freeze_now(monkeypatch, datetime(2026, 10, 9, tzinfo=timezone.utc))
        repo = _make_repo(
            get_period_usage=[_period_row()],
            get_tenant_tier_usage_breakdown=[_quota_row(task_type="nmt", total_units=5.0, quota_snap=0.0)],
        )
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        assert result.data[0].tierBreakdown[0].taskTypes[0].quota.percentageUsed == 100.0

    async def test_no_quota_row_is_null(self):
        repo = _make_repo(get_period_usage=[_period_row()], get_tenant_tier_usage_breakdown=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        assert result.data[0].tierBreakdown[0].taskTypes[0].quota is None

    async def test_task_type_with_only_a_monthly_quota_shows_zero_period_usage(self, monkeypatch):
        """The quota bar still shows on a day the task type wasn't used yet."""
        _freeze_now(monkeypatch, datetime(2026, 10, 9, tzinfo=timezone.utc))
        repo = _make_repo(
            get_period_usage=[_period_row(task_type="nmt")],
            get_tenant_tier_usage_breakdown=[_quota_row(task_type="asr", total_units=3.0, quota_snap=60.0)],
        )
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        item = result.data[0]
        types = {t.taskType: t for t in item.tierBreakdown[0].taskTypes}
        assert types["asr"].periodUsage.model_dump() == {"units": 0, "cost": 0, "breakdown": None}
        assert types["asr"].quota.used == 3
        assert item.usage.taskTypeCount == 1   # used in the period: nmt only

    async def test_tiers_ordered_by_first_activity(self):
        rows = [
            _period_row(tier_id="2", first_seen=datetime(2026, 10, 9, 3, tzinfo=timezone.utc)),
            _period_row(tier_id="1", task_type="tts", first_seen=datetime(2026, 10, 9, 1, tzinfo=timezone.utc)),
        ]
        repo = _make_repo(get_period_usage=rows, get_tenant_tier_usage_breakdown=[])
        result = await UsageService(repo).get_tenant_list(_TODAY, None, None, None)
        assert [t.tierName for t in result.data[0].tierBreakdown] == ["Pro", "Enterprise"]


@pytest.mark.asyncio
class TestGetTenantDetail:
    async def test_period_item_with_budget_window(self):
        effective_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
        repo = _make_repo(
            get_period_usage=[_llm_row()],
            get_tenant_tier_usage_breakdown=[],
            get_tenant_budgets=_budgets(_budget_row(tenant_id="1", budget_effective_from=effective_from)),
        )
        result = await UsageService(repo).get_tenant_detail("1", _TODAY, auth_db=None)

        assert result.period.key == "today"
        assert result.periodSpend == 0.42
        assert result.budget.basis == "all_time"
        assert result.budget.budgetEffectiveFrom == effective_from
        # Same instant, written in IST like every other dashboard timestamp.
        assert result.budget.budgetEffectiveFrom.utcoffset().total_seconds() == 5.5 * 3600
        assert result.model_dump(mode="json")["budget"]["budgetEffectiveFrom"] == "2026-08-01T05:30:00+05:30"
        assert result.budget.spent == 300
        repo.get_period_usage.assert_awaited_once_with(_TODAY, tenant_ids=["1"], task_type_ids=None)

    async def test_no_usage_still_returns_the_institution(self, monkeypatch):
        _freeze_now(monkeypatch, datetime(2026, 10, 9, tzinfo=timezone.utc))
        repo = _make_repo(
            get_period_usage=[],
            get_tenant_tier_usage_breakdown=[_quota_row(task_type="nmt", total_units=40.0, quota_snap=200.0)],
            get_tenant_budgets=_budgets(_budget_row(tenant_id="1", tier_id="2")),
        )
        result = await UsageService(repo).get_tenant_detail("1", _TODAY, auth_db=None)

        assert result.periodSpend == 0
        assert (result.tier, result.tierId) == ("Enterprise", "2")   # current tier
        assert result.usage.taskTypeCount == 0
        task = result.tierBreakdown[0].taskTypes[0]
        assert task.periodUsage.units == 0 and task.quota.used == 40

    async def test_unknown_institution_is_404(self):
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        repo = _make_repo(get_period_usage=[])
        with pytest.raises(EntityNotFoundError):
            await UsageService(repo).get_tenant_detail("999", _TODAY, auth_db=auth_db)


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
