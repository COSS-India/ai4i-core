"""ai4i_core.kafka.notification_settings_cache.refresh_all

config.thresholds has been stored in two shapes over time: the pre-migration
dict keyed by percent-as-string ({"70": false, ...}), and the current list of
{"percentage": int, "active": bool} bands (platform-core-service's
catalog_service.py). A row still holding the old shape must not blow up
refresh_all — the try/except around it would otherwise swallow the error,
leave _rows empty, and silently disable every notification (not just
thresholds), since is_notification_enabled/get_threshold_bands/get_channels
all read from this same cache for all 9 catalog rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from ai4i_core.kafka import notification_settings_cache as cache


@dataclass
class _Row:
    id: int
    name: str
    recipient_roles: Dict[str, bool]
    channels: List[str]
    config: Dict[str, Any]


class _Result:
    def __init__(self, rows: List[_Row]):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows: List[_Row]):
        self._rows = rows

    async def execute(self, _stmt):
        return _Result(self._rows)


@pytest.fixture(autouse=True)
def _reset_cache_state():
    cache._rows = {}
    cache._loaded_at = 0.0
    yield
    cache._rows = {}
    cache._loaded_at = 0.0


class TestActiveThresholdPercentages:
    def test_new_list_shape(self):
        thresholds = [
            {"percentage": 70, "active": True},
            {"percentage": 80, "active": False},
            {"percentage": 90, "active": True},
        ]
        assert cache._active_threshold_percentages(thresholds) == [70, 90]

    def test_old_dict_shape(self):
        thresholds = {"70": True, "80": False, "90": True}
        assert cache._active_threshold_percentages(thresholds) == [70, 90]

    def test_empty_list(self):
        assert cache._active_threshold_percentages([]) == []

    def test_empty_dict(self):
        assert cache._active_threshold_percentages({}) == []


@pytest.mark.asyncio
class TestRefreshAllToleratesBothShapes:
    async def test_new_shape_row_loads_correctly(self):
        rows = [
            _Row(
                id=10, name="QUOTA_THRESHOLD", recipient_roles={"ADMIN": True},
                channels=["EMAIL"],
                config={"thresholds": [
                    {"percentage": 70, "active": True},
                    {"percentage": 90, "active": False},
                ]},
            ),
        ]
        await cache.refresh_all(_FakeDb(rows))
        assert cache._rows["QUOTA_THRESHOLD"]["threshold_bands"] == [70]

    async def test_old_dict_shape_row_does_not_break_the_whole_refresh(self):
        # A row still holding the pre-migration shape must not raise inside
        # refresh_all — that would leave _rows empty and take down every
        # notification type's is_notification_enabled check, not just this
        # row's own thresholds.
        rows = [
            _Row(
                id=10, name="QUOTA_THRESHOLD", recipient_roles={"ADMIN": True},
                channels=["EMAIL"], config={"thresholds": {"70": True, "90": False}},
            ),
            _Row(
                id=1, name="TIER_ASSIGNED", recipient_roles={"ADMIN": True},
                channels=["EMAIL"], config={},
            ),
        ]
        await cache.refresh_all(_FakeDb(rows))
        assert cache._rows["QUOTA_THRESHOLD"]["threshold_bands"] == [70]
        # The unrelated row in the same batch must have loaded too — proof
        # the whole refresh didn't abort/rollback to an empty cache.
        assert "TIER_ASSIGNED" in cache._rows

    async def test_mixed_batch_of_old_and_new_shaped_rows(self):
        rows = [
            _Row(
                id=10, name="QUOTA_THRESHOLD", recipient_roles={}, channels=["EMAIL"],
                config={"thresholds": {"70": True}},
            ),
            _Row(
                id=11, name="BUDGET_THRESHOLD", recipient_roles={}, channels=["EMAIL"],
                config={"thresholds": [{"percentage": 80, "active": True}]},
            ),
        ]
        await cache.refresh_all(_FakeDb(rows))
        assert cache._rows["QUOTA_THRESHOLD"]["threshold_bands"] == [70]
        assert cache._rows["BUDGET_THRESHOLD"]["threshold_bands"] == [80]
