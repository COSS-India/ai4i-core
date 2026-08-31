"""Unit tests for UsageService — hierarchical tenant/tier/task-type aggregation.

All DB I/O is mocked via AsyncMock; no running services required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.pay_per_use.usage_service import UsageService


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
    """Stand-in for a get_tenant_budgets value — budget_limit/available_balance/tier_id.
    tier_id is only consumed by get_tenant_detail's zero-usage fallback (to show the
    tenant's actual assigned tier instead of "Unassigned"); every other caller ignores it.

    The real UsageRepository.get_tenant_budgets always returns {} now (its one data
    source, ppu_tenant_tier_assignments, has been dropped — see that method's own
    docstring), so a non-empty dict here is a scenario the real repo can no longer
    produce. Kept for tests that exercise _resolve_budget/_merge_tier_and_budget's own
    render logic directly, independent of what the repo currently returns."""
    defaults = dict(
        tenant_id="t1", budget_limit=Decimal("1000"), available_balance=Decimal("700"),
        tier_id="1",
    )
    return _row(**{**defaults, **kwargs})


def _budgets(*rows) -> dict:
    return {r.tenant_id: r for r in rows}


def _usage_row(**kwargs):
    defaults = dict(
        tenant_id="t1", tier_id="1", tier_name="Pro",
        inference_name="llm", total_units=100.0, total_cost=Decimal("50"),
        quota_snap=200.0,
    )
    return _row(**{**defaults, **kwargs})


# ── get_summary ───────────────────────────────────────────────────────────────

class TestGetSummary:
    """get_summary(tier_id=None) — the unfiltered path — gets its prior-month total via
    the single-query get_total_cost_for_month, never touching tenant resolution for the
    previous month. get_summary(tier_id=<id>) still needs full tenant-scoped resolution
    for both months, since tier_id scopes by tenant, not by usage row (see TestGetSummaryFiltered).
    """

    @pytest.mark.asyncio
    async def test_total_spend_and_active_tenants(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(),
            get_total_cost_for_month=0.0,
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.totalSpend == 50.0
        assert result.activeTenants == 1
        assert result.spendByModelTaskType[0].spend == 50.0
        assert result.spendByModelTaskType[0].consumption == 100.0

    @pytest.mark.asyncio
    async def test_budget_exceeded_tenant_is_counted(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row(total_cost=Decimal("50"))],
            get_tenant_budgets=_budgets(_budget_row(budget_limit=Decimal("10"))),
            get_total_cost_for_month=0.0,
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.budgetExceededTenants == 1

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_row_is_not_falsely_exceeded(self):
        """A tenant with usage but no budget row (the only case now — see
        _budget_row) has no budget figure at all — must not be treated as
        budget=0 and therefore always 'exceeded' the moment they have any spend."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row(total_cost=Decimal("50"))],
            get_tenant_budgets=_budgets(),  # no row for t1
            get_total_cost_for_month=0.0,
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        # unknown budget != a budget of 0 -- excluded from the count, not flagged as
        # exceeded, matching the 0%-used (not "over budget") treatment in the tenant
        # list/detail view for the same missing-budget-row case (see _resolve_budget).
        assert result.budgetExceededTenants == 0

    @pytest.mark.asyncio
    async def test_spend_change_percent_none_when_no_prior_spend(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tenant_budgets=_budgets(),
            get_total_cost_for_month=0.0,
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.spendChangePercent is None

    @pytest.mark.asyncio
    async def test_spend_change_percent_computed_against_prior_month(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row(total_cost=Decimal("150"))],
            get_tenant_budgets=_budgets(),
            get_total_cost_for_month=100.0,
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        # (150 - 100) / 100 * 100 = 50.0
        assert result.spendChangePercent == 50.0
        repo.get_total_cost_for_month.assert_called_once_with()
        repo.get_tenant_tier_usage_breakdown.assert_called_once()  # current month only

    @pytest.mark.asyncio
    async def test_percentage_sums_to_100_across_task_types(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(inference_name="llm", total_cost=Decimal("75")),
                _usage_row(inference_name="asr", total_cost=Decimal("25")),
            ],
            get_tenant_budgets=_budgets(),
            get_total_cost_for_month=0.0,
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        total_pct = sum(i.percentage for i in result.spendByModelTaskType)
        assert abs(total_pct - 100.0) < 0.2

    @pytest.mark.asyncio
    async def test_allocated_and_remaining_budget_summed_across_tenants(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row(tenant_id="t1"), _tier_row(tenant_id="t2")],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", total_cost=Decimal("50")),
                _usage_row(tenant_id="t2", total_cost=Decimal("30")),
            ],
            get_tenant_budgets=_budgets(
                _budget_row(tenant_id="t1", budget_limit=Decimal("1000"), available_balance=Decimal("700")),
                _budget_row(tenant_id="t2", budget_limit=Decimal("500"), available_balance=Decimal("200")),
            ),
            get_total_cost_for_month=0.0,
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
            get_total_cost_for_month=0.0,
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
            get_total_cost_for_month=0.0,
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
            get_total_cost_for_month=0.0,
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
                _usage_row(inference_name="llm", total_units=100.0, total_cost=Decimal("30"), quota_snap=200.0),
                _usage_row(inference_name="asr", total_units=10.0, total_cost=Decimal("20"), quota_snap=50.0),
            ],
            get_tenant_budgets=_budgets(),
            get_total_cost_for_month=0.0,
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
            get_total_cost_for_month=0.0,
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.spendByModelTaskType[0].consumption == 150.0
        assert result.spendByModelTaskType[0].allocated == 100.0


class TestGetSummaryFiltered:
    """get_summary(tier_id=<id>) must keep using full tenant resolution for the prior
    month too, since tier_id scopes by "who was on this tier," not by usage row."""

    @pytest.mark.asyncio
    async def test_spend_change_percent_uses_tenant_resolution_when_tier_id_set(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=_Seq([
                [_usage_row(total_cost=Decimal("150"))],
                [_usage_row(total_cost=Decimal("100"))],
            ]),
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_summary("2026-06", tier_id="1")

        assert result.spendChangePercent == 50.0
        assert repo.get_tenant_tier_usage_breakdown.call_count == 2
        assert not repo.get_total_cost_for_month.called


# ── get_tenant_list ───────────────────────────────────────────────────────────

class TestGetTenantList:
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
        assert item.spend == 50.0
        assert item.budget.limit == 1000.0
        assert item.budget.remaining == 700.0
        # single distinct task type -> auto-populated even without a filter
        assert item.usage.taskTypeCount == 1
        assert item.usage.consumed == 100.0
        assert item.usage.quotaLimit == 200.0
        assert len(item.tierBreakdown) == 1
        assert item.tierBreakdown[0].taskTypes[0].percentage == 100.0

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_row_shows_zero_budget(self):
        """A tenant with usage this month but no budget row (the only case now
        — see _budget_row) must show budget=0, not error/crash."""
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
                _usage_row(tier_id="1", tier_name="Pro", total_cost=Decimal("30")),
                _usage_row(tier_id="2", tier_name="Enterprise", total_cost=Decimal("20")),
            ],
            get_tier_first_seen=[
                _row(tenant_id="t1", tier_id="2", first_seen=datetime(2026, 6, 15, tzinfo=timezone.utc)),
                _row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 6, 1, tzinfo=timezone.utc)),
            ],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.spend == 50.0
        assert [tb.tierId for tb in item.tierBreakdown] == ["1", "2"]

    @pytest.mark.asyncio
    async def test_model_task_type_filter_narrows_usage_but_not_spend(self):
        """model_task_type only affects the flat `usage` quota-bar fields — spend and
        tierBreakdown always reflect the tenant's full period totals."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(inference_name="llm", total_units=100.0, total_cost=Decimal("30"), quota_snap=200.0),
                _usage_row(inference_name="asr", total_units=50.0, total_cost=Decimal("20"), quota_snap=None),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, "asr", auth_db=None)

        item = result.data[0]
        assert item.spend == 50.0  # full period total, unaffected by the filter
        assert len(item.tierBreakdown[0].taskTypes) == 2  # both task types still present
        assert item.usage.consumed == 50.0  # narrowed to "asr" only
        assert item.usage.quotaLimit is None

    @pytest.mark.asyncio
    async def test_hierarchical_build_only_runs_for_paginated_page(self):
        """Sorting/pagination must happen before the expensive per-tenant build — so
        tier_first_seen, tenant-name resolution, and budget lookup should only be
        called for the tenants on the requested page, not every matching tenant."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[
                _tier_row(tenant_id="t1"),
                _tier_row(tenant_id="t2"),
                _tier_row(tenant_id="t3"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", total_cost=Decimal("10")),
                _usage_row(tenant_id="t2", total_cost=Decimal("90")),
                _usage_row(tenant_id="t3", total_cost=Decimal("50")),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list(
            "2026-06", None, None, auth_db=None, sort_order="desc", limit=1, offset=0
        )

        assert [item.tenantId for item in result.data] == ["t2"]
        assert result.total == 3
        # only the top-1 tenant (t2) should have been resolved/built, not t1/t3
        repo.get_tier_first_seen.assert_called_once_with(["t2"])
        repo.get_tenant_budgets.assert_called_once_with("2026-06", ["t2"])

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
        repo = _make_repo(
            get_tenants_with_usage_tier=[
                _tier_row(tenant_id="t1"),
                _tier_row(tenant_id="t2"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", total_cost=Decimal("10")),
                _usage_row(tenant_id="t2", total_cost=Decimal("90")),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None, sort_order="desc")

        assert [item.tenantId for item in result.data] == ["t2", "t1"]

    @pytest.mark.asyncio
    async def test_sort_order_asc_by_spend(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[
                _tier_row(tenant_id="t1"),
                _tier_row(tenant_id="t2"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", total_cost=Decimal("10")),
                _usage_row(tenant_id="t2", total_cost=Decimal("90")),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None, sort_order="asc")

        assert [item.tenantId for item in result.data] == ["t1", "t2"]

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
                _usage_row(tenant_id="t1", total_cost=Decimal("10")),
                _usage_row(tenant_id="t2", total_cost=Decimal("90")),
                _usage_row(tenant_id="t3", total_cost=Decimal("50")),
            ],
            get_tier_first_seen=[],
            get_tenant_budgets=_budgets(),
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
        budget row present (see _budget_row — the real repo can no longer produce
        one, but this pins _resolve_tier_name's own render logic) must show that
        tier, not "Unassigned" — there's no usage to derive a tier from, but the
        tenant does have one."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[],
            get_tenant_budgets=_budgets(_budget_row(tenant_id="t1", tier_id="2")),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.tier == "Enterprise"
        assert result.tierId == "2"
        # still a zero-usage item otherwise — only tier/tierId change
        assert result.spend == 0.0
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
        assert result.spend == 50.0
        assert result.budget.limit == 1000.0
        assert result.budget.remaining == 700.0
        assert result.usage.consumed == 100.0
        assert result.usage.quotaLimit == 200.0
        assert len(result.tierBreakdown) == 1

    @pytest.mark.asyncio
    async def test_tenant_with_no_budget_row_shows_zero_budget(self):
        """A tenant with usage this month but no budget row (the only case now —
        see _budget_row) must still show usage/tier data, just with budget=0."""
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.tier == "Pro"
        assert result.spend == 50.0
        assert result.budget.limit == 0.0
        assert result.budget.remaining == 0.0

    @pytest.mark.asyncio
    async def test_multi_task_type_percentages_sum_to_100(self):
        repo = _make_repo(
            get_tenants_with_usage_tier=[_tier_row()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(inference_name="llm", total_cost=Decimal("75")),
                _usage_row(inference_name="asr", total_cost=Decimal("25")),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
            get_tenant_budgets=_budgets(),
        )
        svc = UsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        task_types = result.tierBreakdown[0].taskTypes
        total_pct = sum(t.percentage for t in task_types)
        assert abs(total_pct - 100.0) < 0.2
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

        with caplog.at_level(logging.WARNING, logger="app.services.pay_per_use.usage_service"):
            result = await _resolve_tenant_names(["1", "2"], broken_db)

        assert result == {}
        assert any("connection refused" in r.message for r in caplog.records)

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
