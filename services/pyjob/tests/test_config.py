"""bootstrap.config: settings that must agree with each other."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bootstrap.config import PyJobSettings  # noqa: E402


def test_unset_retention_follows_the_rollup_lookback():
    """usage_events keeps yesterday and the lookback days: every day the
    rollup re-reads still has its rows."""
    assert PyJobSettings(EVENT_USAGE_ROLLUP=4).usage_events_retention_days == 5
    assert PyJobSettings(EVENT_USAGE_ROLLUP=0).usage_events_retention_days == 1


def test_default_retention_covers_only_the_rollup_lookback():
    assert PyJobSettings().usage_events_retention_days == 3


def test_usage_events_retention_when_set_replaces_the_lookback():
    assert PyJobSettings(USAGE_EVENTS_RETENTION=10).usage_events_retention_days == 10
    assert PyJobSettings(USAGE_EVENTS_RETENTION=5, EVENT_USAGE_ROLLUP=4).usage_events_retention_days == 5


def test_usage_events_retention_must_exceed_the_rollup_lookback():
    """A day the rollup still re-reads must keep its usage_events rows."""
    with pytest.raises(ValueError, match="USAGE_EVENTS_RETENTION"):
        PyJobSettings(USAGE_EVENTS_RETENTION=2, EVENT_USAGE_ROLLUP=2)
