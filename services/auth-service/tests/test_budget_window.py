"""app.utils.budget_window.is_budget_window_expired — the single source of
truth for "has this tenant's budget effective window ended", shared by
validation.py's _cached_budget_window_is_expired (compares the value
cached in the API key's own payload) and APIKeyService.create_api_key (the
create-time gate, reading tenants.budget_effective_to directly), so the two
can never disagree on what "expired" means.
"""
from datetime import datetime, timedelta, timezone

from app.utils import budget_window
from app.utils.budget_window import is_budget_window_expired


class TestIsBudgetWindowExpired:
    def test_none_never_expires(self) -> None:
        assert is_budget_window_expired(None) is False

    def test_past_is_expired(self) -> None:
        assert is_budget_window_expired(datetime.now(timezone.utc) - timedelta(seconds=1)) is True

    def test_future_is_not_expired(self) -> None:
        assert is_budget_window_expired(datetime.now(timezone.utc) + timedelta(days=1)) is False

    def test_naive_datetime_treated_as_utc_past(self) -> None:
        naive_past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
        assert is_budget_window_expired(naive_past) is True

    def test_naive_datetime_treated_as_utc_future(self) -> None:
        naive_future = (datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None)
        assert is_budget_window_expired(naive_future) is False

    def test_non_utc_timezone_is_converted_before_comparing(self) -> None:
        """A +05:30 timestamp that's already past in UTC terms must be
        expired even though its own wall-clock time looks "later"."""
        ist = timezone(timedelta(hours=5, minutes=30))
        past_in_ist = (datetime.now(timezone.utc) - timedelta(minutes=1)).astimezone(ist)
        assert is_budget_window_expired(past_in_ist) is True

    def test_exact_instant_counts_as_expired(self, monkeypatch) -> None:
        """"Reached" is inclusive (>=) — the exact instant
        budget_effective_to falls on must already read as expired, not
        require "now" to have strictly passed it. datetime.now is frozen
        here so the comparison is genuinely == and not just "a few
        microseconds later than the value under test."""
        frozen = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen

        monkeypatch.setattr(budget_window, "datetime", _FrozenDatetime)
        assert is_budget_window_expired(frozen) is True
