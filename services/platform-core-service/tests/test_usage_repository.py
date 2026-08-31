"""Unit tests for UsageRepository.get_tier_names()'s in-process TTL cache,
and for the get_tenant_budgets lookup-instant selection.

The cache lives at module scope (app.repositories.pay_per_use.usage_repository),
not on the instance, since UsageRepository is constructed fresh per request. That
means state can leak between test functions unless it's reset — hence the autouse
fixture below.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
