"""Unit tests for the Usage Dashboard's period filter (app.utils.usage_period)."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.utils.metering_promql_builder import AbsoluteRange
from app.utils.usage_period import period_from_request, resolve_period

# 14:20:37 IST on 2026-10-09.
_NOW = datetime(2026, 10, 9, 8, 50, 37, tzinfo=timezone.utc)


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _resolve(period=None, from_=None, to=None, now=_NOW):
    return resolve_period(period, from_, to, now=now)


def _assert_invalid(message: str, *args, **kwargs) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _resolve(*args, **kwargs)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"code": "INVALID_PERIOD", "message": message}


class TestPeriods:
    def test_default_is_today(self):
        assert _resolve().key == "today"

    def test_today_is_ist_midnight_to_now_floored_to_the_minute(self):
        p = _resolve("today")
        assert (p.from_date, p.to_date) == (date(2026, 10, 9), date(2026, 10, 9))
        assert (p.start, p.end) == (_utc(2026, 10, 8, 18, 30), _utc(2026, 10, 9, 8, 50))
        assert not p.uses_daily_usage

    def test_today_in_the_first_minute_after_midnight_is_not_empty(self):
        p = _resolve("today", now=_utc(2026, 10, 8, 18, 30, 20))
        assert p.end == _utc(2026, 10, 8, 18, 30, 20) and p.end > p.start

    def test_today_follows_the_ist_date_not_the_utc_one(self):
        """00:10 IST on the 10th is still the 9th in UTC."""
        p = _resolve("today", now=_utc(2026, 10, 9, 18, 40))
        assert p.from_date == date(2026, 10, 10)
        assert p.start == _utc(2026, 10, 9, 18, 30)

    def test_yesterday_is_the_previous_ist_day(self):
        p = _resolve("yesterday")
        assert (p.from_date, p.to_date) == (date(2026, 10, 8), date(2026, 10, 8))
        assert (p.start, p.end) == (_utc(2026, 10, 7, 18, 30), _utc(2026, 10, 8, 18, 30))
        assert p.uses_daily_usage

    def test_last_7_days_ends_yesterday(self):
        p = _resolve("last_7_days")
        assert (p.from_date, p.to_date) == (date(2026, 10, 2), date(2026, 10, 8))
        assert (p.start, p.end) == (_utc(2026, 10, 1, 18, 30), _utc(2026, 10, 8, 18, 30))
        assert p.days == 7

    def test_custom_covers_whole_ist_days_inclusive(self):
        p = _resolve("custom", "2026-09-01", "2026-09-30")
        assert (p.start, p.end) == (_utc(2026, 8, 31, 18, 30), _utc(2026, 9, 30, 18, 30))
        assert p.days == 30

    def test_custom_single_day(self):
        p = _resolve("custom", "2026-10-08", "2026-10-08")
        assert p.days == 1 and p.to_date == date(2026, 10, 8)


class TestAbsoluteRange:
    def test_today_compares_with_the_same_clock_span_yesterday(self):
        assert _resolve("today").absolute_range == AbsoluteRange(
            start=_utc(2026, 10, 8, 18, 30), end=_utc(2026, 10, 9, 8, 50), previous_shift_seconds=86_400,
        )

    def test_whole_day_ranges_compare_with_the_days_before(self):
        assert _resolve("last_7_days").absolute_range.previous_shift_seconds == 7 * 86_400


class TestSchema:
    def test_period_block_serializes_with_from(self):
        dumped = _resolve("last_7_days").to_schema().model_dump(by_alias=True)
        assert dumped == {
            "key": "last_7_days", "from": "2026-10-02", "to": "2026-10-08",
            "start": "2026-10-02T00:00:00+05:30", "end": "2026-10-09T00:00:00+05:30",
            "timezone": "Asia/Kolkata",
            "dataFrom": "2026-10-02T00:00:00+05:30", "partial": False, "estimated": False, "estimatedUntil": None,
        }

    def test_data_since_inside_the_period_is_partial(self):
        period = _resolve("last_7_days")
        # 2026-10-05 00:00 IST
        block = period.to_schema(datetime(2026, 10, 4, 18, 30, tzinfo=timezone.utc))
        assert (block.dataFrom, block.partial) == ("2026-10-05T00:00:00+05:30", True)

    def test_data_since_before_the_period_covers_it(self):
        block = _resolve("last_7_days").to_schema(datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert (block.dataFrom, block.partial) == ("2026-10-02T00:00:00+05:30", False)

    def test_no_data_at_all_or_only_after_the_period(self):
        """No data → dataFrom null: the UI shows "no data", not zero usage."""
        period = _resolve("last_7_days")
        assert (period.to_schema(None).dataFrom, period.to_schema(None).partial) == (None, True)
        after = period.to_schema(period.end)
        assert (after.dataFrom, after.partial) == (None, True)

    def test_estimates_up_to_where_they_end(self):
        period = _resolve("last_7_days")
        # Backfilled up to 2026-10-04 11:30 IST.
        block = period.to_schema(period.start, datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc))
        assert (block.estimated, block.estimatedUntil) == (True, "2026-10-04T11:30:00+05:30")

    def test_estimates_past_the_period_end_at_its_end(self):
        period = _resolve("last_7_days")
        block = period.to_schema(period.start, datetime(2026, 12, 1, tzinfo=timezone.utc))
        assert (block.estimated, block.estimatedUntil) == (True, "2026-10-09T00:00:00+05:30")

    def test_nothing_estimated(self):
        period = _resolve("last_7_days")
        for block in (
            period.to_schema(period.start),                     # no backfill
            period.to_schema(period.start, period.start),       # estimates end where the period starts
            period.to_schema(None, period.end),                 # no data at all
        ):
            assert (block.estimated, block.estimatedUntil) == (False, None)

    def test_cache_part_differs_by_range(self):
        assert _resolve("today").cache_part != _resolve("yesterday").cache_part


class TestValidation:
    def test_unknown_period(self):
        _assert_invalid("period must be one of: today, yesterday, last_7_days, custom.", "24h")

    def test_custom_needs_both_dates(self):
        _assert_invalid("from and to are required when period is custom.", "custom", "2026-10-01")
        _assert_invalid("from and to are required when period is custom.", "custom", None, "2026-10-01")

    def test_dates_only_with_custom(self):
        _assert_invalid("from and to are only allowed when period is custom.", "today", "2026-10-01", "2026-10-02")
        _assert_invalid("from and to are only allowed when period is custom.", None, "2026-10-01", None)

    def test_bad_date_format(self):
        _assert_invalid("from must be a date in YYYY-MM-DD format.", "custom", "01-10-2026", "2026-10-02")
        _assert_invalid("to must be a date in YYYY-MM-DD format.", "custom", "2026-10-01", "2026-10-02T00:00:00")

    def test_to_must_be_yesterday_or_earlier(self):
        _assert_invalid("to must be yesterday or earlier; use period=today for today.", "custom", "2026-10-01", "2026-10-09")
        _assert_invalid("to must be yesterday or earlier; use period=today for today.", "custom", "2026-10-01", "2027-01-01")

    def test_from_after_to(self):
        _assert_invalid("from must not be after to.", "custom", "2026-10-05", "2026-10-04")

    def test_from_before_2000(self):
        _assert_invalid("from must be on or after 2000-01-01.", "custom", "1999-12-31", "2000-01-05")

    def test_range_longer_than_366_days(self):
        _assert_invalid("The custom range must not exceed 366 days.", "custom", "2025-10-01", "2026-10-02")
        assert _resolve("custom", "2025-10-03", "2026-10-03").days == 366


class TestRemovedParams:
    @pytest.mark.parametrize("name", ["window", "billing_period"])
    def test_removed_param_is_422(self, name):
        request = SimpleNamespace(query_params={name: "x"})
        with pytest.raises(HTTPException) as exc_info:
            period_from_request(request, None, None, None, now=_NOW)
        assert exc_info.value.detail == {
            "code": "INVALID_PERIOD", "message": f"{name} is no longer supported; use period.",
        }

    def test_request_without_query_params_is_accepted(self):
        assert period_from_request(SimpleNamespace(), "yesterday", None, None, now=_NOW).key == "yesterday"
