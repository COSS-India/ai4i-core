"""bootstrap.config: settings that must agree with each other."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bootstrap.config import PyJobSettings  # noqa: E402


def test_retention_must_exceed_the_rollup_lookback():
    """A day the rollup still re-reads must keep its usage_events rows."""
    with pytest.raises(ValueError, match="USAGE_EVENTS_RETENTION_DAYS"):
        PyJobSettings(USAGE_EVENTS_RETENTION_DAYS=2, USAGE_ROLLUP_LOOKBACK_DAYS=2)
    assert PyJobSettings(USAGE_EVENTS_RETENTION_DAYS=3, USAGE_ROLLUP_LOOKBACK_DAYS=2)


def test_default_retention_covers_only_the_rollup_lookback():
    assert PyJobSettings().USAGE_EVENTS_RETENTION_DAYS == 3
