"""period_source: which table a Usage Dashboard period reads, and the BRIN
index that serves usage_events time-range scans."""
import pytest

from app.core.config import settings
from app.models.pay_per_use.daily_usage import DailyUsage
from app.models.pay_per_use.usage_event import UsageEvent
from app.repositories.pay_per_use.period_usage import period_source
from app.utils.usage_period import resolve_period


@pytest.mark.parametrize("key", ["today", "yesterday", "last_7_days"])
def test_usage_events_for_every_period_until_the_rollup_is_on(monkeypatch, key):
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", False)
    assert period_source(resolve_period(key, None, None)).model is UsageEvent


def test_past_periods_read_daily_usage_once_the_rollup_is_on(monkeypatch):
    monkeypatch.setattr(settings, "usage_daily_rollup_enabled", True)
    assert period_source(resolve_period("yesterday", None, None)).model is DailyUsage
    assert period_source(resolve_period("today", None, None)).model is UsageEvent


def test_usage_events_range_is_half_open():
    """[start, end): an event at exactly 00:00 IST belongs to the next day."""
    sql = str(period_source(resolve_period("yesterday", None, None)).in_period)
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

    sql = str(period_source(resolve_period("today", None, None)).in_period)
    assert f"NOT ({REQUEST_ROWS})" in sql
