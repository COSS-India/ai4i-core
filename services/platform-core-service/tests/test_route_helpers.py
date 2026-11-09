"""Unit tests for shared route helpers: range_start, range_end_exclusive."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.utils.route_helpers import range_end_exclusive, range_start


class TestRangeStart:
    def test_date_becomes_midnight_utc(self):
        result = range_start(date(2026, 3, 15))
        assert result == datetime(2026, 3, 15, 0, 0, 0, tzinfo=timezone.utc)

    def test_datetime_with_tz_returned_unchanged(self):
        dt = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
        assert range_start(dt) == dt

    def test_naive_datetime_gets_utc_attached(self):
        naive = datetime(2026, 3, 15, 10, 30)
        result = range_start(naive)
        assert result.tzinfo == timezone.utc
        assert result.replace(tzinfo=None) == naive


class TestRangeEndExclusive:
    def test_date_becomes_next_midnight_utc(self):
        result = range_end_exclusive(date(2026, 3, 15))
        assert result == datetime(2026, 3, 16, 0, 0, 0, tzinfo=timezone.utc)

    def test_datetime_treated_as_exact_instant(self):
        dt = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
        assert range_end_exclusive(dt) == range_start(dt)

    def test_date_range_spans_exactly_one_day(self):
        d = date(2026, 6, 1)
        assert range_end_exclusive(d) - range_start(d) == timedelta(days=1)
