"""Unit tests for UsageRepository.get_tier_names()'s in-process TTL cache,
and for the get_tenant_budgets lookup-instant selection.

The cache lives at module scope (app.repositories.pay_per_use.usage_repository),
not on the instance, since UsageRepository is constructed fresh per request. That
means state can leak between test functions unless it's reset — hence the autouse
fixture below.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.pay_per_use import usage_repository as repo_module
from app.repositories.pay_per_use.usage_repository import (
    UsageRepository,
    _budget_lookup_instant,
    _end_of_month,
)


@pytest.fixture(autouse=True)
def _reset_tier_cache():
    """Ensure each test starts from a cold cache and leaves none behind."""
    repo_module._tier_cache = {}
    repo_module._tier_cache_loaded_at = None
    yield
    repo_module._tier_cache = {}
    repo_module._tier_cache_loaded_at = None


def _make_db(rows: list[SimpleNamespace]) -> AsyncMock:
    """Fake AsyncSession whose execute() returns rows shaped like the
    (Tier.id, Tier.name) tuples get_tier_names() selects."""
    db = AsyncMock()
    result = SimpleNamespace(all=lambda: rows)
    db.execute = AsyncMock(return_value=result)
    return db


def _freeze_now(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    """Pin repo_module's datetime.now() so _budget_lookup_instant is deterministic."""

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(repo_module, "datetime", _FrozenDateTime)


class TestBudgetLookupInstant:
    """_budget_lookup_instant picks "now" for the current billing_month (so a
    just-topped-up assignment that hasn't reached the calendar month's end is
    still found) and _end_of_month for any past billing_month (a closed month
    gets a stable, frozen snapshot instead of drifting with wall-clock time)."""

    def test_current_month_uses_now(self, monkeypatch):
        now = datetime(2026, 7, 21, 9, 52, 37, tzinfo=timezone.utc)
        _freeze_now(monkeypatch, now)

        assert _budget_lookup_instant("2026-07") == now

    def test_past_month_uses_end_of_month(self, monkeypatch):
        now = datetime(2026, 7, 21, 9, 52, 37, tzinfo=timezone.utc)
        _freeze_now(monkeypatch, now)

        assert _budget_lookup_instant("2026-06") == _end_of_month("2026-06")

    def test_current_month_instant_falls_inside_assignment_ending_at_midnight(
        self, monkeypatch
    ):
        """Regression: an assignment valid through "2026-07-31T00:00:00Z" (the
        shape reassign_tier/revise_budget actually write) never reaches
        _end_of_month("2026-07")'s 23:59:59.999999 instant, which is why a
        freshly topped-up tenant's budget was reading back as 0. Comparing
        against "now" instead — while July is still the current month — fixes
        that without needing effective_to's shape to change at all."""
        now = datetime(2026, 7, 21, 9, 52, 37, tzinfo=timezone.utc)
        _freeze_now(monkeypatch, now)
        effective_from = datetime(2026, 7, 21, 9, 52, 37, tzinfo=timezone.utc)
        effective_to = datetime(2026, 7, 31, 0, 0, 0, tzinfo=timezone.utc)

        lookup_instant = _budget_lookup_instant("2026-07")

        assert effective_from <= lookup_instant < effective_to


class TestGetTenantBudgets:
    """Exact-bug-scenario regression test: ppu_tenant_tier_assignments was
    dropped (AI4IDS-2923); get_tenant_budgets previously queried it directly
    and raised UndefinedTableError in production (reproduced live against
    /usage-summary, /usage-tenants, /usage-tenant). Reconstructed from
    tenants.allocated_budget + budget_usage (via api_key/applications), so
    these tests exercise the actual cross-DB query logic, not a mocked
    repository interface.
    """

    @staticmethod
    def _auth_db(side_effects: list) -> MagicMock:
        auth_db = MagicMock()
        auth_db.execute = AsyncMock(side_effect=side_effects)
        return auth_db

    @staticmethod
    def _rows(rows: list) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: rows)

    @pytest.mark.asyncio
    async def test_empty_tenant_ids_returns_empty_without_querying(self):
        repo = UsageRepository(db=AsyncMock())
        auth_db = self._auth_db([])

        result = await repo.get_tenant_budgets("2026-08", [], auth_db)

        assert result == {}
        auth_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_auth_db_none_returns_empty(self):
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-08", ["2"], None)

        assert result == {}

    @pytest.mark.asyncio
    async def test_normal_case_computes_budget_from_allocated_minus_spend(self):
        auth_db = self._auth_db(
            [
                self._rows(
                    [SimpleNamespace(id=2, allocated_budget=Decimal("1000000.00"), tier_id=None)]
                ),  # tenants
                self._rows(
                    [SimpleNamespace(id=39, tenant_id=2), SimpleNamespace(id=40, tenant_id=2)]
                ),  # applications
                self._rows(
                    [
                        SimpleNamespace(id=10, application_id=39),
                        SimpleNamespace(id=11, application_id=39),
                        SimpleNamespace(id=12, application_id=40),
                    ]
                ),  # api_key
            ]
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=self._rows(
                [
                    SimpleNamespace(api_key_id=10, api_key_budget_used=Decimal("70000.00")),
                    SimpleNamespace(api_key_id=11, api_key_budget_used=Decimal("30000.00")),
                    SimpleNamespace(api_key_id=12, api_key_budget_used=Decimal("90000.00")),
                ]
            )
        )
        repo = UsageRepository(db=db)

        result = await repo.get_tenant_budgets("2026-08", ["2"], auth_db)

        assert set(result.keys()) == {"2"}
        budget = result["2"]
        assert budget.budget_limit == Decimal("1000000.00")
        assert budget.available_balance == Decimal("810000.00")  # 1,000,000 - (70000+30000+90000)
        assert budget.tier_id is None

    @pytest.mark.asyncio
    async def test_tenant_not_in_auth_db_is_absent_from_result(self):
        auth_db = self._auth_db([self._rows([])])  # tenants query returns nothing

        repo = UsageRepository(db=AsyncMock())
        result = await repo.get_tenant_budgets("2026-08", ["999"], auth_db)

        assert result == {}

    @pytest.mark.asyncio
    async def test_tenant_with_no_applications_has_zero_spend(self):
        auth_db = self._auth_db(
            [
                self._rows(
                    [SimpleNamespace(id=5, allocated_budget=Decimal("50000.00"), tier_id=None)]
                ),  # tenants
                self._rows([]),  # applications — none
            ]
        )
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-08", ["5"], auth_db)

        budget = result["5"]
        assert budget.budget_limit == Decimal("50000.00")
        assert budget.available_balance == Decimal("50000.00")

    @pytest.mark.asyncio
    async def test_non_digit_tenant_id_short_circuits_without_querying(self):
        auth_db = self._auth_db([])
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-08", ["not-a-number"], auth_db)

        assert result == {}
        auth_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_auth_db_failure_degrades_to_empty_not_a_crash(self):
        """Unlike application_usage_service's money-figure loads (fixed
        separately to let failures propagate instead of swallowing them),
        get_tenant_budgets keeps this method's own pre-existing graceful-
        degrade contract: a tenant absent from the returned dict already
        reads as budget_limit=0/available_balance=0/has_budget=False via
        _resolve_budget — that's this method's original behavior, preserved
        here, not a new decision introduced by this fix."""
        auth_db = MagicMock()
        auth_db.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
        repo = UsageRepository(db=AsyncMock())

        result = await repo.get_tenant_budgets("2026-08", ["2"], auth_db)

        assert result == {}
