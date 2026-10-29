"""app/services/cache_service.py — CacheService.set_service_access.

inference-service keeps each resolved service in memory for CACHE_TTL_SECONDS,
so an unpublish or Tier change used to take up to that long (longer with
several platform-core pods) to stop requests. platform-core now also writes
``core:service:{service_id}:access`` = {"is_published", "tier_ids"} to Redis
whenever the service is rebuilt in its own cache, and inference-service reads
that key on every resolve. This file pins the key, the value and the TTL, and
that a Redis failure never fails the caller.
"""

from __future__ import annotations

import json

import pytest

from app.services.cache_service import CacheService


class _FakeRedis:
    def __init__(self, setex_raises: Exception | None = None):
        self.writes: list[tuple] = []
        self._setex_raises = setex_raises

    async def setex(self, key, ttl, value):
        if self._setex_raises is not None:
            raise self._setex_raises
        self.writes.append((key, ttl, value))
        return True


class TestSetServiceAccess:
    @pytest.mark.asyncio
    async def test_writes_flags_under_the_access_key(self) -> None:
        redis = _FakeRedis()

        await CacheService(redis_client=redis).set_service_access("llm-a/v1", False, ["tier-1"])

        ((key, _, value),) = redis.writes
        assert key == "core:service:llm-a/v1:access"
        assert json.loads(value) == {"is_published": False, "tier_ids": ["tier-1"]}

    @pytest.mark.asyncio
    async def test_key_matches_inference_service_reader_exactly(self) -> None:
        """Cross-service contract: inference-service's resolver reads
        "core:service:" + service_id + ":access". Renaming either side makes
        inference fall back to its in-memory copy silently."""
        redis = _FakeRedis()

        await CacheService(redis_client=redis).set_service_access("svc-xyz", True, [])

        assert redis.writes[0][0] == "core:service:" + "svc-xyz" + ":access"

    @pytest.mark.asyncio
    async def test_ttl_outlives_inference_in_memory_cache(self) -> None:
        """inference falls back to its cached copy on a missing key; that is
        only safe if the key outlives that copy (300 s)."""
        redis = _FakeRedis()

        await CacheService(redis_client=redis).set_service_access("svc", True, [])

        assert redis.writes[0][1] >= 300

    @pytest.mark.asyncio
    async def test_no_tiers_is_written_as_an_empty_list(self) -> None:
        redis = _FakeRedis()

        await CacheService(redis_client=redis).set_service_access("svc", True, None)

        assert json.loads(redis.writes[0][2]) == {"is_published": True, "tier_ids": []}

    @pytest.mark.asyncio
    async def test_redis_failure_is_swallowed_not_raised(self) -> None:
        """The DB write already committed; a Redis hiccup degrades to
        inference's in-memory TTL, never fails the update request."""
        redis = _FakeRedis(setex_raises=ConnectionError("redis down"))

        await CacheService(redis_client=redis).set_service_access("svc", False, [])
