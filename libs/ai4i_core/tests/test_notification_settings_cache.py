"""ai4i_core.kafka.notification_settings_cache.refresh_all

config.thresholds has been stored in two shapes over time: the pre-migration
dict keyed by percent-as-string ({"70": false, ...}), and the current list of
{"percentage": int, "active": bool} bands (platform-core-service's
catalog_service.py). A row still holding the old shape must not blow up
refresh_all — the try/except around it would otherwise swallow the error,
leave the Redis cache unset, and silently disable every notification (not
just thresholds), since is_notification_enabled/get_threshold_bands/
get_channels all read from this same cache for all 9 catalog rows.

The cache itself now lives in Redis (shared across every service instance)
instead of a process-local dict, so these tests drive it through a fake
Redis client rather than poking module globals directly.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List

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


class _FakeRedis:
    """Minimal in-memory stand-in for the pieces of redis.asyncio this
    module uses: GET/SET with ex=, DELETE. TTL is tracked but never expired
    within a single test — expiry itself is Redis's job, not this module's."""

    def __init__(self):
        self.store: Dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.set_calls.append((key, value, ex))

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis_client", lambda: redis)
    return redis


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
    async def test_new_shape_row_loads_correctly(self, fake_redis):
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
        loaded = json.loads(fake_redis.store[cache.CACHE_KEY])
        assert loaded["QUOTA_THRESHOLD"]["threshold_bands"] == [70]

    async def test_old_dict_shape_row_does_not_break_the_whole_refresh(self, fake_redis):
        # A row still holding the pre-migration shape must not raise inside
        # refresh_all — that would leave the Redis cache unset and take down
        # every notification type's is_notification_enabled check, not just
        # this row's own thresholds.
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
        loaded = json.loads(fake_redis.store[cache.CACHE_KEY])
        assert loaded["QUOTA_THRESHOLD"]["threshold_bands"] == [70]
        # The unrelated row in the same batch must have loaded too — proof
        # the whole refresh didn't abort/rollback to an empty cache.
        assert "TIER_ASSIGNED" in loaded

    async def test_mixed_batch_of_old_and_new_shaped_rows(self, fake_redis):
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
        loaded = json.loads(fake_redis.store[cache.CACHE_KEY])
        assert loaded["QUOTA_THRESHOLD"]["threshold_bands"] == [70]
        assert loaded["BUDGET_THRESHOLD"]["threshold_bands"] == [80]

    async def test_stores_with_ttl(self, fake_redis):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", recipient_roles={}, channels=[], config={}),
        ]
        await cache.refresh_all(_FakeDb(rows))
        _key, _value, ttl = fake_redis.set_calls[-1]
        assert ttl == cache.TTL_SECONDS

    async def test_refresh_failure_leaves_previous_cache_untouched(self, fake_redis):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", recipient_roles={"ADMIN": True}, channels=["EMAIL"], config={}),
        ]
        await cache.refresh_all(_FakeDb(rows))
        before = fake_redis.store[cache.CACHE_KEY]

        class _BrokenDb:
            async def execute(self, _stmt):
                raise RuntimeError("db unreachable")

        await cache.refresh_all(_BrokenDb())
        assert fake_redis.store[cache.CACHE_KEY] == before


@pytest.mark.asyncio
class TestReads:
    async def test_is_notification_enabled_reloads_on_cache_miss(self, fake_redis):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", recipient_roles={"ADMIN": True}, channels=["EMAIL"], config={}),
        ]
        assert await cache.is_notification_enabled(_FakeDb(rows), "TIER_ASSIGNED") is True

    async def test_is_notification_enabled_false_when_no_role_selected(self, fake_redis):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", recipient_roles={"ADMIN": False}, channels=["EMAIL"], config={}),
        ]
        assert await cache.is_notification_enabled(_FakeDb(rows), "TIER_ASSIGNED") is False

    async def test_is_notification_enabled_false_for_unknown_name(self, fake_redis):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", recipient_roles={"ADMIN": True}, channels=["EMAIL"], config={}),
        ]
        assert await cache.is_notification_enabled(_FakeDb(rows), "NOT_A_REAL_NAME") is False

    async def test_reads_do_not_requery_db_once_cache_is_warm(self, fake_redis):
        calls = {"n": 0}

        class _CountingDb:
            async def execute(self, _stmt):
                calls["n"] += 1
                return _Result([
                    _Row(id=1, name="TIER_ASSIGNED", recipient_roles={"ADMIN": True}, channels=["EMAIL"], config={}),
                ])

        db = _CountingDb()
        await cache.is_notification_enabled(db, "TIER_ASSIGNED")
        await cache.get_channels(db, "TIER_ASSIGNED")
        await cache.get_notification_id(db, "TIER_ASSIGNED")
        assert calls["n"] == 1

    async def test_invalidate_forces_next_read_to_reload(self, fake_redis):
        calls = {"n": 0}

        class _CountingDb:
            async def execute(self, _stmt):
                calls["n"] += 1
                return _Result([
                    _Row(id=1, name="TIER_ASSIGNED", recipient_roles={"ADMIN": True}, channels=["EMAIL"], config={}),
                ])

        db = _CountingDb()
        await cache.is_notification_enabled(db, "TIER_ASSIGNED")
        await cache.invalidate()
        await cache.is_notification_enabled(db, "TIER_ASSIGNED")
        assert calls["n"] == 2

    async def test_get_threshold_bands_empty_for_unknown_name(self, fake_redis):
        rows = [
            _Row(id=1, name="TIER_ASSIGNED", recipient_roles={}, channels=[], config={}),
        ]
        assert await cache.get_threshold_bands(_FakeDb(rows), "NOT_A_REAL_NAME") == []
