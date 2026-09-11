"""app.utils.budget_window.is_budget_window_expired — the single source of
truth for "has this tenant's budget effective window ended", shared by
validation.py's _cached_budget_window_is_expired (compares the value
cached in the API key's own payload), APIKeyService.create_api_key (the
create-time gate, reading tenants.budget_effective_to directly), and
tenant_service.py's own window-assignment validators — so none of them can
ever disagree on what "expired" means.

budget_effective_to is the LAST day the window is usable, not the instant
it starts being unusable — an inclusive calendar-day comparison (UTC), not
a wall-clock instant. A tenant with budget_effective_to = 2026-10-10 is
still fully servable all through Oct 10 UTC (any time of day), and only
becomes expired once Oct 11 UTC begins.
"""
from datetime import datetime, timedelta, timezone

from app.utils import budget_window
from app.utils.budget_window import is_budget_window_expired


def _frozen_now(monkeypatch, frozen: datetime) -> None:
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(budget_window, "datetime", _FrozenDatetime)


class TestIsBudgetWindowExpired:
    def test_none_never_expires(self) -> None:
        assert is_budget_window_expired(None) is False

    def test_a_full_day_in_the_past_is_expired(self) -> None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert is_budget_window_expired(yesterday) is True

    def test_a_full_day_in_the_future_is_not_expired(self) -> None:
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        assert is_budget_window_expired(tomorrow) is False

    def test_effective_to_is_the_last_usable_day_not_the_first_expired_one(
        self, monkeypatch
    ) -> None:
        """The exact scenario this fix is for: budget_effective_to = Oct 10
        — the tenant must still be servable at any time on Oct 10 itself,
        including right up to the last second of that day."""
        effective_to = datetime(2026, 10, 10, 0, 0, 0, tzinfo=timezone.utc)
        _frozen_now(monkeypatch, datetime(2026, 10, 10, 23, 59, 59, tzinfo=timezone.utc))
        assert is_budget_window_expired(effective_to) is False

    def test_expiry_begins_the_day_after_effective_to(self, monkeypatch) -> None:
        """The other half of the same scenario: the very first moment of
        Oct 11 — one second past midnight — is when it actually expires."""
        effective_to = datetime(2026, 10, 10, 0, 0, 0, tzinfo=timezone.utc)
        _frozen_now(monkeypatch, datetime(2026, 10, 11, 0, 0, 0, tzinfo=timezone.utc))
        assert is_budget_window_expired(effective_to) is True

    def test_exact_same_instant_is_not_expired(self, monkeypatch) -> None:
        """budget_effective_to given as a precise instant (not midnight) is
        still just "that calendar day" — reaching that exact instant must
        not expire the tenant early; only the following day does."""
        frozen = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        _frozen_now(monkeypatch, frozen)
        assert is_budget_window_expired(frozen) is False

    def test_naive_datetime_treated_as_utc_past(self) -> None:
        naive_past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
        assert is_budget_window_expired(naive_past) is True

    def test_naive_datetime_treated_as_utc_future(self) -> None:
        naive_future = (datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None)
        assert is_budget_window_expired(naive_future) is False

    def test_non_utc_timezone_is_converted_to_utc_before_taking_the_date(
        self, monkeypatch
    ) -> None:
        """A timestamp whose LOCAL calendar date differs from its UTC
        calendar date must be compared by the UTC date, not the local one.
        02:00 IST (UTC+5:30) on Jan 2 is 20:30 UTC on Jan 1 — a naive
        implementation that read .date() before converting would see
        "Jan 2" and wrongly treat "now" (frozen to Jan 2 00:00 UTC) as the
        same day (not yet expired), when the UTC day has already moved on."""
        ist = timezone(timedelta(hours=5, minutes=30))
        effective_to_ist = datetime(2026, 1, 2, 2, 0, 0, tzinfo=ist)  # == 2026-01-01T20:30:00Z
        _frozen_now(monkeypatch, datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc))
        assert is_budget_window_expired(effective_to_ist) is True
