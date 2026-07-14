"""Unit tests for PPUUsageService — hierarchical tenant/tier/task-type aggregation.

All DB I/O is mocked via AsyncMock; no running services required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.pay_per_use.ppu_usage_service import PPUUsageService


class _Seq(list):
    """Marks a list of per-call return values, applied via AsyncMock(side_effect=...),
    for methods invoked more than once with different args in a single service call
    (e.g. get_tenant_tier_usage_breakdown, hit for both the current and the previous
    billing month inside get_summary)."""


def _make_repo(**method_returns) -> MagicMock:
    """Return a mock repository whose async methods return the given values."""
    repo = MagicMock()
    for method, value in method_returns.items():
        if isinstance(value, _Seq):
            setattr(repo, method, AsyncMock(side_effect=list(value)))
        else:
            setattr(repo, method, AsyncMock(return_value=value))
    return repo


def _row(**kwargs):
    """Lightweight stand-in for a SQLAlchemy Row."""
    return SimpleNamespace(**kwargs)


def _assignment(**kwargs):
    defaults = dict(
        tenant_id="t1", tier_id="1", tier_name="Pro",
        budget_limit=Decimal("1000"), available_balance=Decimal("700"),
    )
    return _row(**{**defaults, **kwargs})


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
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_total_cost_for_month=0.0,
        )
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.totalSpend == 50.0
        assert result.activeTenants == 1
        assert result.spendByModelTaskType[0].spend == 50.0
        assert result.spendByModelTaskType[0].consumption == 100.0

    @pytest.mark.asyncio
    async def test_budget_exceeded_tenant_is_counted(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment(budget_limit=Decimal("10"))],
            get_tenant_tier_usage_breakdown=[_usage_row(total_cost=Decimal("50"))],
            get_total_cost_for_month=0.0,
        )
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.budgetExceededTenants == 1

    @pytest.mark.asyncio
    async def test_spend_change_percent_none_when_no_prior_spend(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_total_cost_for_month=0.0,
        )
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.spendChangePercent is None

    @pytest.mark.asyncio
    async def test_spend_change_percent_computed_against_prior_month(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[_usage_row(total_cost=Decimal("150"))],
            get_total_cost_for_month=100.0,
        )
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        # (150 - 100) / 100 * 100 = 50.0
        assert result.spendChangePercent == 50.0
        repo.get_total_cost_for_month.assert_called_once_with("2026-05")
        repo.get_tenant_tier_usage_breakdown.assert_called_once()  # current month only

    @pytest.mark.asyncio
    async def test_percentage_sums_to_100_across_task_types(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(inference_name="llm", total_cost=Decimal("75")),
                _usage_row(inference_name="asr", total_cost=Decimal("25")),
            ],
            get_total_cost_for_month=0.0,
        )
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        total_pct = sum(i.percentage for i in result.spendByModelTaskType)
        assert abs(total_pct - 100.0) < 0.2


class TestGetSummaryFiltered:
    """get_summary(tier_id=<id>) must keep using full tenant resolution for the prior
    month too, since tier_id scopes by "who was on this tier," not by usage row."""

    @pytest.mark.asyncio
    async def test_spend_change_percent_uses_tenant_resolution_when_tier_id_set(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=_Seq([
                [_usage_row(total_cost=Decimal("150"))],
                [_usage_row(total_cost=Decimal("100"))],
            ]),
        )
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06", tier_id="1")

        assert result.spendChangePercent == 50.0
        assert repo.get_tenant_tier_usage_breakdown.call_count == 2
        assert not repo.get_total_cost_for_month.called


# ── get_tenant_list ───────────────────────────────────────────────────────────

class TestGetTenantList:
    @pytest.mark.asyncio
    async def test_single_tenant_single_tier_single_task_type(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
        )
        svc = PPUUsageService(repo)
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
    async def test_remaining_quota_clamped_at_zero_when_overused(self):
        """remaining must never go negative, even when consumed exceeds the quota —
        both on the flat `usage` block and on each tierBreakdown taskType entry."""
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(total_units=150.0, quota_snap=100.0),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.usage.remaining == 0.0
        assert item.tierBreakdown[0].taskTypes[0].remaining == 0.0

    @pytest.mark.asyncio
    async def test_zero_quota_with_usage_shows_fully_exhausted(self):
        """A 0 quota is a deliberate 'blocked for this cycle' setting, not missing data.
        Any usage against it must show percentage=100, not 0 (which `if quota` would
        give since 0.0 is falsy)."""
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(total_units=5.0, quota_snap=0.0),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        usage = result.data[0].usage
        assert usage.quotaLimit == 0.0
        assert usage.remaining == 0.0
        assert usage.percentage == 100.0

    @pytest.mark.asyncio
    async def test_zero_quota_with_no_usage_shows_zero_percent(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(total_units=0.0, quota_snap=0.0),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        assert result.data[0].usage.percentage == 0.0

    @pytest.mark.asyncio
    async def test_multi_tier_breakdown_ordered_oldest_first(self):
        """A tenant reassigned mid-period shows both tiers, oldest tier first, and spend
        is the sum across every tier they held that month."""
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment(tier_id="2", tier_name="Enterprise")],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tier_id="1", tier_name="Pro", total_cost=Decimal("30")),
                _usage_row(tier_id="2", tier_name="Enterprise", total_cost=Decimal("20")),
            ],
            get_tier_first_seen=[
                _row(tenant_id="t1", tier_id="2", first_seen=datetime(2026, 6, 15, tzinfo=timezone.utc)),
                _row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 6, 1, tzinfo=timezone.utc)),
            ],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.spend == 50.0
        assert [tb.tierId for tb in item.tierBreakdown] == ["1", "2"]

    @pytest.mark.asyncio
    async def test_model_task_type_filter_narrows_usage_but_not_spend(self):
        """model_task_type only affects the flat `usage` quota-bar fields — spend and
        tierBreakdown always reflect the tenant's full period totals."""
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(inference_name="llm", total_units=100.0, total_cost=Decimal("30"), quota_snap=200.0),
                _usage_row(inference_name="asr", total_units=50.0, total_cost=Decimal("20"), quota_snap=None),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, "asr", auth_db=None)

        item = result.data[0]
        assert item.spend == 50.0  # full period total, unaffected by the filter
        assert len(item.tierBreakdown[0].taskTypes) == 2  # both task types still present
        assert item.usage.consumed == 50.0  # narrowed to "asr" only
        assert item.usage.quotaLimit is None

    @pytest.mark.asyncio
    async def test_sort_order_desc_by_spend(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[
                _assignment(tenant_id="t1"),
                _assignment(tenant_id="t2"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", total_cost=Decimal("10")),
                _usage_row(tenant_id="t2", total_cost=Decimal("90")),
            ],
            get_tier_first_seen=[],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None, sort_order="desc")

        assert [item.tenantId for item in result.data] == ["t2", "t1"]

    @pytest.mark.asyncio
    async def test_sort_order_asc_by_spend(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[
                _assignment(tenant_id="t1"),
                _assignment(tenant_id="t2"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", total_cost=Decimal("10")),
                _usage_row(tenant_id="t2", total_cost=Decimal("90")),
            ],
            get_tier_first_seen=[],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None, sort_order="asc")

        assert [item.tenantId for item in result.data] == ["t1", "t2"]

    @pytest.mark.asyncio
    async def test_no_assignments_returns_empty_response(self):
        repo = _make_repo(get_tenant_tier_as_of_period_end=[])
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        assert result.data == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_pagination_slices_page_but_total_is_full_count(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[
                _assignment(tenant_id="t1"),
                _assignment(tenant_id="t2"),
                _assignment(tenant_id="t3"),
            ],
            get_tenant_tier_usage_breakdown=[
                _usage_row(tenant_id="t1", total_cost=Decimal("10")),
                _usage_row(tenant_id="t2", total_cost=Decimal("90")),
                _usage_row(tenant_id="t3", total_cost=Decimal("50")),
            ],
            get_tier_first_seen=[],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list(
            "2026-06", None, None, auth_db=None, sort_order="desc", limit=1, offset=1
        )

        # sorted desc by spend: t2(90), t3(50), t1(10) -> offset=1, limit=1 -> just t3
        assert [item.tenantId for item in result.data] == ["t3"]
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_offset_past_end_returns_empty_page_with_full_total(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None, offset=10, limit=10)

        assert result.data == []
        assert result.total == 1


# ── get_tenant_detail ─────────────────────────────────────────────────────────

class TestGetTenantDetail:
    @pytest.mark.asyncio
    async def test_raises_when_no_assignment(self):
        from app.core.exceptions import EntityNotFoundError

        repo = _make_repo(get_tenant_tier_as_of_period_end=[])
        svc = PPUUsageService(repo)
        with pytest.raises(EntityNotFoundError):
            await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

    @pytest.mark.asyncio
    async def test_single_tenant_hierarchical_shape(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[_usage_row()],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.tenantId == "t1"
        assert result.spend == 50.0
        assert result.budget.limit == 1000.0
        assert result.budget.remaining == 700.0
        assert result.usage.consumed == 100.0
        assert result.usage.quotaLimit == 200.0
        assert len(result.tierBreakdown) == 1

    @pytest.mark.asyncio
    async def test_multi_task_type_percentages_sum_to_100(self):
        repo = _make_repo(
            get_tenant_tier_as_of_period_end=[_assignment()],
            get_tenant_tier_usage_breakdown=[
                _usage_row(inference_name="llm", total_cost=Decimal("75")),
                _usage_row(inference_name="asr", total_cost=Decimal("25")),
            ],
            get_tier_first_seen=[_row(tenant_id="t1", tier_id="1", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        task_types = result.tierBreakdown[0].taskTypes
        total_pct = sum(t.percentage for t in task_types)
        assert abs(total_pct - 100.0) < 0.2
        # multiple distinct task types -> nothing to disambiguate, usage stays unset
        assert result.usage.taskTypeCount == 2
        assert result.usage.consumed is None


# ── _resolve_tenant_names ─────────────────────────────────────────────────────

class TestResolveTenantNames:
    @pytest.mark.asyncio
    async def test_logs_warning_on_auth_db_failure(self, caplog):
        """Auth DB exception must be logged, not silently swallowed."""
        import logging
        from app.services.pay_per_use.ppu_usage_service import _resolve_tenant_names

        broken_db = MagicMock()
        broken_db.execute = AsyncMock(side_effect=Exception("connection refused"))

        with caplog.at_level(logging.WARNING, logger="app.services.pay_per_use.ppu_usage_service"):
            result = await _resolve_tenant_names(["1", "2"], broken_db)

        assert result == {}
        assert any("connection refused" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_auth_db(self):
        from app.services.pay_per_use.ppu_usage_service import _resolve_tenant_names
        result = await _resolve_tenant_names(["1"], auth_db=None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_resolves_integer_tenant_ids(self):
        """Numeric string IDs must reach the DB and return the org name mapping."""
        from app.services.pay_per_use.ppu_usage_service import _resolve_tenant_names

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
        from app.services.pay_per_use.ppu_usage_service import _resolve_tenant_names

        db = MagicMock()
        result = await _resolve_tenant_names(["abc", "uuid-xyz"], auth_db=db)

        assert result == {}
        db.execute.assert_not_called()
