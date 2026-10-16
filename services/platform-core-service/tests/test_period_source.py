"""period_sources: which table(s) a Usage Dashboard period reads, and the BRIN
index that serves usage_events time-range scans."""
from datetime import date, datetime, timezone

import pytest

from app.core.config import settings
from app.models.pay_per_use.daily_usage import DailyUsage
from app.models.pay_per_use.usage_event import UsageEvent
from app.repositories.pay_per_use.period_usage import period_sources
from app.utils.usage_period import ist_midnight, resolve_period

# 16 Oct 2026, 15:20 IST.
NOW = datetime(2026, 10, 16, 9, 50, tzinfo=timezone.utc)


def _dashboard(key, from_=None, to=None):
    """The period as the dashboard resolves it (today included)."""
    return resolve_period(key, from_, to, now=NOW, include_today=True)


def _models(period):
    return [s.model for s in period_sources(period)]


@pytest.mark.parametrize("key", ["today", "yesterday", "last_7_days"])
def test_usage_events_for_every_period_until_the_rollup_is_on(monkeypatch, key):
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", False)
    assert _models(_dashboard(key)) == [UsageEvent]


def test_past_periods_read_daily_usage_once_the_rollup_is_on(monkeypatch):
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", True)
    assert _models(_dashboard("yesterday")) == [DailyUsage]
    assert _models(_dashboard("today")) == [UsageEvent]
    assert _models(_dashboard("custom", "2026-10-01", "2026-10-15")) == [DailyUsage]


def test_a_period_ending_today_reads_its_past_days_from_daily_usage_and_today_from_usage_events(monkeypatch):
    """Last 7 days and a custom range ending today: daily_usage for the whole
    days before today, usage_events for today up to now (not rolled up yet)."""
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", True)
    for period in (_dashboard("last_7_days"), _dashboard("custom", "2026-10-01", "2026-10-16")):
        daily, events = period_sources(period)
        assert (daily.model, events.model) == (DailyUsage, UsageEvent)
        daily_sql = str(daily.in_period.compile(compile_kwargs={"literal_binds": True}))
        assert f"'{period.from_date}'" in daily_sql and "'2026-10-15'" in daily_sql
        events_bounds = events.in_period.compile().params
        assert ist_midnight(date(2026, 10, 16)) in events_bounds.values()
        assert period.end in events_bounds.values()


def test_a_custom_range_of_just_today_reads_usage_events(monkeypatch):
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", True)
    assert _models(_dashboard("custom", "2026-10-16", "2026-10-16")) == [UsageEvent]


def test_usage_events_range_is_half_open():
    """[start, end): an event at exactly 00:00 IST belongs to the next day."""
    sql = str(period_sources(_dashboard("today"))[0].in_period)
    assert ">=" in sql and "<" in sql and "<=" not in sql


def test_brin_index_on_occurred_at():
    (index,) = [i for i in UsageEvent.__table__.indexes if i.name == "ix_usage_events_occurred_at_brin"]
    assert [c.name for c in index.columns] == ["occurred_at"]
    assert index.dialect_options["postgresql"]["using"] == "brin"
    # Unsummarised ranges match every query; see migration cf2715437b4f.
    assert index.dialect_options["postgresql"]["with"] == {"autosummarize": "on"}


def test_budget_filter_is_built_from_request_rows():
    """The Budget tab leaves out request rows by the one REQUEST_ROWS definition."""
    from app.models.pay_per_use.usage_event import REQUEST_ROWS

    sql = str(period_sources(_dashboard("today"))[0].in_period)
    assert f"NOT ({REQUEST_ROWS})" in sql
