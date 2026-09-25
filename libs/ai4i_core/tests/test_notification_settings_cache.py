"""ai4i_core.kafka.notification_settings_cache.refresh_all / is_notification_enabled

config.thresholds has been stored in two shapes over time: the pre-migration
dict keyed by percent-as-string ({"70": false, ...}), and the current list of
{"percentage": int, "active": bool} bands (platform-core-service's
catalog_service.py). A row still holding the old shape must not blow up
refresh_all — the try/except around it would otherwise swallow the error,
leave _rows empty, and silently disable every notification (not just
thresholds), since is_notification_enabled/get_threshold_bands/get_channels
all read from this same cache for all 9 catalog rows.

recipient_roles is gone (e2a4c6b8d0f2_add_scope_drop_recipient_roles_
notification_catalog.py) — enablement is now scope (GLOBAL/INSTITUTION)
plus, for an INSTITUTION row, a direct point query against
tenant_notification_subscription (not part of the cached blob — see the
module's own docstring for why).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from ai4i_core.kafka import notification_settings_cache as cache


@dataclass
class _Row:
    id: int
    name: str
    scope: str
    channels: List[str]
    config: Dict[str, Any]


class _Result:
    def __init__(self, rows: List[Any]):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


@dataclass
class _SubRow:
    subscribed: bool


class _FakeDb:
    """Answers both queries this module ever issues against `db`: the
    catalog SELECT (refresh_all) and, for an INSTITUTION-scope row, the
    tenant_notification_subscription point query (is_notification_enabled).
    Distinguished by a substring check on the statement text — good enough
    for a fake, real dispatch is SQLAlchemy's job."""

    def __init__(self, rows: List[_Row], subscriptions: Optional[Dict[tuple, bool]] = None):
        self._rows = rows
        self._subscriptions = subscriptions or {}

    async def execute(self, stmt, params: Optional[dict] = None):
        text = str(stmt)
        if "tenant_notification_subscription" in text:
            key = (params["notification_id"], params["tenant_id"])
            if key not in self._subscriptions:
                return _Result([])
            return _Result([_SubRow(subscribed=self._subscriptions[key])])
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
                id=10, name="QUOTA_THRESHOLD", scope="GLOBAL",
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
                id=10, name="QUOTA_THRESHOLD", scope="GLOBAL",
                channels=["EMAIL"], config={"thresholds": {"70": True, "90": False}},
            ),
            _Row(
                id=1, name="TIER_ASSIGNED", scope="INSTITUTION",
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
                id=10, name="QUOTA_THRESHOLD", scope="GLOBAL", channels=["EMAIL"],
                config={"thresholds": {"70": True}},
            ),
            _Row(
                id=11, name="BUDGET_THRESHOLD", scope="GLOBAL", channels=["EMAIL"],
                config={"thresholds": [{"percentage": 80, "active": True}]},
            ),
        ]
        await cache.refresh_all(_FakeDb(rows))
        assert cache._rows["QUOTA_THRESHOLD"]["threshold_bands"] == [70]
        assert cache._rows["BUDGET_THRESHOLD"]["threshold_bands"] == [80]


@pytest.mark.asyncio
class TestIsNotificationEnabled:
    async def test_global_scope_is_always_enabled(self):
        rows = [
            _Row(id=1, name="TIER_CHANGED", scope="GLOBAL", channels=["EMAIL"], config={}),
        ]
        assert await cache.is_notification_enabled(_FakeDb(rows), "TIER_CHANGED") is True

    async def test_institution_scope_enabled_when_tenant_subscribed(self):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", scope="INSTITUTION", channels=["EMAIL"], config={}),
        ]
        db = _FakeDb(rows, subscriptions={(1, "79"): True})
        assert await cache.is_notification_enabled(db, "TIER_ASSIGNED", "79") is True

    async def test_institution_scope_disabled_when_tenant_not_subscribed(self):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", scope="INSTITUTION", channels=["EMAIL"], config={}),
        ]
        db = _FakeDb(rows, subscriptions={(1, "79"): False})
        assert await cache.is_notification_enabled(db, "TIER_ASSIGNED", "79") is False

    async def test_institution_scope_disabled_when_no_subscription_row(self):
        # Row absence for this (notification, tenant) pair reads as
        # "unsubscribed" — same as subscription_service's own read path.
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", scope="INSTITUTION", channels=["EMAIL"], config={}),
        ]
        db = _FakeDb(rows, subscriptions={})
        assert await cache.is_notification_enabled(db, "TIER_ASSIGNED", "79") is False

    async def test_institution_scope_fails_closed_without_tenant_id(self):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", scope="INSTITUTION", channels=["EMAIL"], config={}),
        ]
        db = _FakeDb(rows, subscriptions={(1, "79"): True})
        assert await cache.is_notification_enabled(db, "TIER_ASSIGNED") is False

    async def test_false_for_unknown_name(self):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", scope="INSTITUTION", channels=["EMAIL"], config={}),
        ]
        assert await cache.is_notification_enabled(_FakeDb(rows), "NOT_A_REAL_NAME") is False
