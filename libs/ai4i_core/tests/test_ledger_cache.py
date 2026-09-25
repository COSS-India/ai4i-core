"""ai4i_core.kafka.ledger_cache — the Redis-backed fast-path in front of the
real DB UPSERT in ledger.py.

Redis-backed instead of process-local: a status written by one replica must
be visible to every other replica's pre-check (that's the whole point of
the move — see notification_settings_cache.py's module docstring for the
same rationale). Being wrong here is always safe (falls through to the DB),
so these tests only pin the two things that matter: a genuine HIT actually
skips work, and every kind of miss/error correctly reports "not cached".
"""

from __future__ import annotations

from typing import Dict

import pytest

from ai4i_core.kafka import ledger_cache as cache


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis"):
        self._redis = redis
        self._ops: list[tuple[str, tuple]] = []

    def hset(self, key, field, value):
        self._ops.append(("hset", (key, field, value)))
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", (key, ttl)))
        return self

    async def execute(self):
        for op, args in self._ops:
            if op == "hset":
                key, field, value = args
                self._redis.hashes.setdefault(key, {})[field] = value
            elif op == "expire":
                key, ttl = args
                self._redis.expirations[key] = ttl


class _FakeRedis:
    def __init__(self, hget_raises: Exception | None = None):
        self.hashes: Dict[str, Dict[str, str]] = {}
        self.expirations: Dict[str, int] = {}
        self._hget_raises = hget_raises

    async def hget(self, key, field):
        if self._hget_raises is not None:
            raise self._hget_raises
        return self.hashes.get(key, {}).get(field)

    def pipeline(self):
        return _FakePipeline(self)


@pytest.fixture
def fake_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis_client", lambda: redis)
    return redis


@pytest.mark.asyncio
class TestSetThenMatch:
    async def test_hit_after_set(self, fake_redis):
        await cache.set_cached_status(1, "tenant-a", '{"period":"2026-09"}', "EMAIL", {"value": 70, "delivery": "in_progress"})
        assert await cache.matches_cached_status(1, "tenant-a", '{"period":"2026-09"}', "EMAIL", {"value": 70, "delivery": "sent"}) is True

    async def test_delivery_only_change_still_matches(self, fake_redis):
        # Comparing only "value", never the whole envelope, mirrors the DB's
        # own WHERE clause (ledger.py) — a delivery-only change downstream
        # must never look like a new occurrence to this cache either.
        await cache.set_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": True, "delivery": "in_progress"})
        assert await cache.matches_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": True, "delivery": "failed"}) is True

    async def test_different_value_is_a_miss(self, fake_redis):
        await cache.set_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": 70, "delivery": "in_progress"})
        assert await cache.matches_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": 80, "delivery": "in_progress"}) is False

    async def test_write_sets_a_ttl(self, fake_redis):
        await cache.set_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": 70, "delivery": "in_progress"})
        key = cache._key(1, "tenant-a", "{}", "EMAIL")
        assert fake_redis.expirations[key] == cache.TTL_SECONDS


@pytest.mark.asyncio
class TestMisses:
    async def test_unknown_key_is_a_miss(self, fake_redis):
        assert await cache.matches_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": 70, "delivery": "in_progress"}) is False

    async def test_different_channel_is_a_miss(self, fake_redis):
        await cache.set_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": 70, "delivery": "in_progress"})
        assert await cache.matches_cached_status(1, "tenant-a", "{}", "SMS", {"value": 70, "delivery": "in_progress"}) is False

    async def test_redis_read_error_falls_through_as_a_miss(self, monkeypatch):
        redis = _FakeRedis(hget_raises=RuntimeError("connection reset"))
        monkeypatch.setattr(cache, "get_redis_client", lambda: redis)
        assert await cache.matches_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": 70, "delivery": "in_progress"}) is False

    async def test_redis_write_error_does_not_raise(self, monkeypatch):
        class _BrokenRedis(_FakeRedis):
            def pipeline(self):
                raise RuntimeError("connection reset")

        monkeypatch.setattr(cache, "get_redis_client", lambda: _BrokenRedis())
        # Must not raise — a failed cache write should never break the
        # caller, since the DB UPSERT (ledger.py) is already the source of
        # truth by the time this is called.
        await cache.set_cached_status(1, "tenant-a", "{}", "EMAIL", {"value": 70, "delivery": "in_progress"})


class TestEncodeValue:
    def test_bool_and_int_do_not_collide(self):
        assert cache._encode_value(True) != cache._encode_value(1)
        assert cache._encode_value(False) != cache._encode_value(0)
