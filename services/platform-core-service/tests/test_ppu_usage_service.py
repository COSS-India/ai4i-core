"""Unit tests for PPUUsageService — spend calculation and unit-conversion logic.

All DB I/O is mocked via AsyncMock; no running services required.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.pay_per_use.ppu_usage_service import PPUUsageService


def _make_repo(**method_returns) -> MagicMock:
    """Return a mock repository whose async methods return the given values."""
    repo = MagicMock()
    for method, value in method_returns.items():
        setattr(repo, method, AsyncMock(return_value=value))
    return repo


def _row(**kwargs):
    """Lightweight stand-in for a SQLAlchemy Row."""
    return SimpleNamespace(**kwargs)


# ── get_summary ───────────────────────────────────────────────────────────────

class TestGetSummary:
    @pytest.mark.asyncio
    async def test_spend_via_unit_rate(self):
        """unit_rate path: spend = units * unit_rate (not divided by unit_size first)."""
        repo = _make_repo(get_usage_with_pricing=[
            _row(inference_name="llm", total_units=1_000_000,
                 unit_size=1_000_000, unit_rate=Decimal("0.001"), cost_per_unit=None),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        # spend = 1_000_000 * 0.001 = 1000.0
        assert result.totalSpend == 1000.0
        assert result.spendByModelTaskType[0].spend == 1000.0
        assert result.spendByModelTaskType[0].consumption == 1.0

    @pytest.mark.asyncio
    async def test_spend_via_cost_per_unit(self):
        """cost_per_unit path: spend = consumption * cost_per_unit."""
        repo = _make_repo(get_usage_with_pricing=[
            _row(inference_name="llm", total_units=2_000_000,
                 unit_size=1_000_000, unit_rate=None, cost_per_unit=Decimal("50")),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        # consumption = 2_000_000 / 1_000_000 = 2.0 ; spend = 2.0 * 50 = 100.0
        assert result.spendByModelTaskType[0].consumption == 2.0
        assert result.spendByModelTaskType[0].spend == 100.0

    @pytest.mark.asyncio
    async def test_no_pricing_gives_zero_spend(self):
        """When both unit_rate and cost_per_unit are None, spend is 0."""
        repo = _make_repo(get_usage_with_pricing=[
            _row(inference_name="asr", total_units=500,
                 unit_size=60, unit_rate=None, cost_per_unit=None),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.spendByModelTaskType[0].spend == 0.0
        assert result.totalSpend == 0.0

    @pytest.mark.asyncio
    async def test_percentage_sums_to_100(self):
        """Percentages across all items must add up to 100."""
        repo = _make_repo(get_usage_with_pricing=[
            _row(inference_name="llm", total_units=750_000,
                 unit_size=1_000_000, unit_rate=Decimal("1"), cost_per_unit=None),
            _row(inference_name="asr", total_units=250_000,
                 unit_size=1_000_000, unit_rate=Decimal("1"), cost_per_unit=None),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        total_pct = sum(i.percentage for i in result.spendByModelTaskType)
        assert abs(total_pct - 100.0) < 0.2

    @pytest.mark.asyncio
    async def test_fallback_unit_size_when_none(self):
        """unit_size=None falls back to 1_000_000 so consumption doesn't crash."""
        repo = _make_repo(get_usage_with_pricing=[
            _row(inference_name="llm", total_units=500_000,
                 unit_size=None, unit_rate=None, cost_per_unit=None),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_summary("2026-06")

        assert result.spendByModelTaskType[0].consumption == 0.5


# ── get_tenant_list ───────────────────────────────────────────────────────────

class TestGetTenantList:
    @pytest.mark.asyncio
    async def test_uses_per_service_unit_size_not_default(self):
        """ASR row with unit_size=60: consumption must use 60, not 1_000_000."""
        repo = _make_repo(get_tenant_usages=[
            _row(tenant_id="t1", tier_name="Pro",
                 budget_limit=Decimal("1000"), available_balance=Decimal("700"),
                 total_units=1800, total_cost=Decimal("300"), total_quota=3600, unit_size=60),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, "asr", auth_db=None)

        item = result.data[0]
        # 1800 / 60 = 30 minutes; NOT 1800 / 1_000_000 = 0.0
        assert item.consumptionToDate == 30.0
        assert item.quotaLimit == 60.0  # 3600 / 60

    @pytest.mark.asyncio
    async def test_fallback_to_default_unit_size_when_null(self):
        """unit_size=None (no model_task_type filter): falls back to 1_000_000."""
        repo = _make_repo(get_tenant_usages=[
            _row(tenant_id="t1", tier_name="Pro",
                 budget_limit=Decimal("1000"), available_balance=Decimal("1000"),
                 total_units=500_000, total_cost=Decimal("0"),
                 total_quota=1_000_000, unit_size=None),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.consumptionToDate == 0.5   # 500_000 / 1_000_000
        assert item.quotaLimit == 1.0          # 1_000_000 / 1_000_000

    @pytest.mark.asyncio
    async def test_remaining_budget_calculation(self):
        """spendToDate = sum(cost_accum) for the period; remainingBudget = availableBalance."""
        repo = _make_repo(get_tenant_usages=[
            _row(tenant_id="t1", tier_name="Free",
                 budget_limit=Decimal("500"), available_balance=Decimal("300"),
                 total_units=0, total_cost=Decimal("200"), total_quota=0, unit_size=None),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        item = result.data[0]
        assert item.spendToDate == 200.0
        assert item.remainingBudget == 300.0

    @pytest.mark.asyncio
    async def test_remaining_quota_never_negative(self):
        """remainingQuota must be clamped at 0 when consumption exceeds quota."""
        repo = _make_repo(get_tenant_usages=[
            _row(tenant_id="t1", tier_name="Free",
                 budget_limit=Decimal("1000"), available_balance=Decimal("1000"),
                 total_units=2_000_000, total_cost=Decimal("0"),
                 total_quota=1_000_000, unit_size=1_000_000),
        ])
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_list("2026-06", None, None, auth_db=None)

        assert result.data[0].remainingQuota == 0.0


# ── get_tenant_detail ─────────────────────────────────────────────────────────

class TestGetTenantDetail:
    def _assignment(self, **kwargs):
        defaults = dict(
            budget_limit=Decimal("1000"), available_balance=Decimal("600"),
            tier_name="Pro", total_quota=None,
        )
        return _row(**{**defaults, **kwargs})

    def _breakdown_row(self, **kwargs):
        defaults = dict(
            inference_name="llm", total_units=500_000, unit_size=1_000_000,
            unit_rate=None, cost_per_unit=None, monthly_quota_snap=None,
        )
        return _row(**{**defaults, **kwargs})

    @pytest.mark.asyncio
    async def test_raises_when_no_assignment(self):
        """EntityNotFoundError when tenant has no active tier assignment."""
        from app.core.exceptions import EntityNotFoundError
        repo = _make_repo(get_tenant_assignment=None, get_tenant_period_breakdown=[])
        svc = PPUUsageService(repo)
        with pytest.raises(EntityNotFoundError):
            await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

    @pytest.mark.asyncio
    async def test_single_type_quota_and_consumption(self):
        """Single inference type: top-level quota and consumption use the correct unit_size."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(total_quota=3_000_000_000),
            get_tenant_period_breakdown=[
                self._breakdown_row(
                    inference_name="llm", total_units=500_000_000,
                    unit_size=1_000_000, monthly_quota_snap=3_000_000_000,
                ),
            ],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.consumptionToDate == 500.0        # 500M / 1M
        assert result.quotaLimit == 3000.0              # 3B / 1M
        assert result.remainingQuota == 2500.0          # 3000 - 500
        assert result.quotaUnit != "Units"              # resolved to LLM unit label
        assert len(result.breakdown) == 1
        assert result.breakdown[0].quotaLimit == 3000.0
        assert result.breakdown[0].remainingQuota == 2500.0

    @pytest.mark.asyncio
    async def test_multi_type_top_level_nulled(self):
        """Multi inference type: top-level quota fields are null; per-breakdown fields are set."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(total_quota=5_000_000_000),
            get_tenant_period_breakdown=[
                self._breakdown_row(
                    inference_name="llm", total_units=500_000_000,
                    unit_size=1_000_000, monthly_quota_snap=3_000_000_000,
                ),
                self._breakdown_row(
                    inference_name="asr", total_units=3600,
                    unit_size=60, monthly_quota_snap=18000,
                ),
            ],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.quotaLimit is None
        assert result.consumptionToDate is None
        assert result.remainingQuota is None
        assert result.quotaUnit == "Units"

        llm = next(b for b in result.breakdown if b.modelTaskType == "llm")
        assert llm.quotaLimit == 3000.0     # 3B / 1M
        assert llm.remainingQuota == 2500.0

        asr = next(b for b in result.breakdown if b.modelTaskType == "asr")
        assert asr.quotaLimit == 300.0      # 18000 / 60
        assert asr.consumptionToDate == 60.0  # 3600 / 60
        assert asr.remainingQuota == 240.0

    @pytest.mark.asyncio
    async def test_unlimited_quota_returns_none(self):
        """total_quota=None (no quota rows for tier) → quotaLimit and remainingQuota are None."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(total_quota=None),
            get_tenant_period_breakdown=[
                self._breakdown_row(monthly_quota_snap=None),
            ],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.quotaLimit is None
        assert result.remainingQuota is None
        assert result.breakdown[0].quotaLimit is None
        assert result.breakdown[0].remainingQuota is None

    @pytest.mark.asyncio
    async def test_remaining_quota_clamped_at_zero(self):
        """remainingQuota never goes negative when consumption exceeds the quota."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(total_quota=1_000_000_000),
            get_tenant_period_breakdown=[
                self._breakdown_row(
                    total_units=2_000_000_000, unit_size=1_000_000,
                    monthly_quota_snap=1_000_000_000,
                ),
            ],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.remainingQuota == 0.0
        assert result.breakdown[0].remainingQuota == 0.0

    @pytest.mark.asyncio
    async def test_budget_fields(self):
        """spendToDate = budgetLimit - availableBalance; remainingBudget = availableBalance."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(
                budget_limit=Decimal("5000"), available_balance=Decimal("3500"),
            ),
            get_tenant_period_breakdown=[self._breakdown_row()],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.budgetLimit == 5000.0
        assert result.spendToDate == 1500.0
        assert result.remainingBudget == 3500.0

    @pytest.mark.asyncio
    async def test_empty_breakdown_returns_null_quota(self):
        """No usage rows this month: breakdown is empty, top-level quota fields are None."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(total_quota=1_000_000_000),
            get_tenant_period_breakdown=[],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.breakdown == []
        assert result.consumptionToDate == 0.0  # zero usage, not unknown
        assert result.quotaLimit is None         # no inference type to derive unit_size from
        assert result.remainingQuota is None

    @pytest.mark.asyncio
    async def test_breakdown_percentage_single_type(self):
        """Single inference type: breakdown percentage must be 100.0."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(),
            get_tenant_period_breakdown=[
                self._breakdown_row(
                    inference_name="llm", total_units=1_000_000,
                    unit_size=1_000_000, unit_rate=Decimal("1"),
                ),
            ],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.breakdown[0].percentage == 100.0

    @pytest.mark.asyncio
    async def test_breakdown_percentage_multi_type_sums_to_100(self):
        """Multi inference type: breakdown percentages must sum to 100."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(total_quota=None),
            get_tenant_period_breakdown=[
                self._breakdown_row(
                    inference_name="llm", total_units=750_000,
                    unit_size=1_000_000, unit_rate=Decimal("1"),
                ),
                self._breakdown_row(
                    inference_name="asr", total_units=250_000,
                    unit_size=1_000_000, unit_rate=Decimal("1"),
                ),
            ],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        llm = next(b for b in result.breakdown if b.modelTaskType == "llm")
        asr = next(b for b in result.breakdown if b.modelTaskType == "asr")
        assert llm.percentage == 75.0
        assert asr.percentage == 25.0
        assert abs(llm.percentage + asr.percentage - 100.0) < 0.2

    @pytest.mark.asyncio
    async def test_breakdown_percentage_zero_spend(self):
        """When all spend is zero, percentage must be 0.0 (no division-by-zero)."""
        repo = _make_repo(
            get_tenant_assignment=self._assignment(),
            get_tenant_period_breakdown=[
                self._breakdown_row(unit_rate=None, cost_per_unit=None),
            ],
        )
        svc = PPUUsageService(repo)
        result = await svc.get_tenant_detail("t1", "2026-06", auth_db=None)

        assert result.breakdown[0].percentage == 0.0


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
