"""app/services/cache_service.py — CacheService.invalidate_pricing.

payperuse_consumer._billing.get_service_pricing caches mm_services' pricing
columns under ``ppu:svc:{service_id}`` for up to an hour and never
invalidates that key itself. CacheService.invalidate_pricing is the
platform-core side of the fix: ServiceService.update_service calls it right
after a pricing-relevant DB write commits, so billing re-reads mm_services
on the very next request instead of serving the old rate for up to an hour.

This file pins the cache-service unit in isolation (which key it deletes,
that it never touches the DB, that a Redis failure doesn't raise). The
wiring from update_service is covered separately in test_service_update.py,
and the end-to-end "stale price survives without this call" scenario is
covered in kafka-consumers' test_billing.py (the actual reader).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.cache_service import CacheService


class _FakeRedis:
    def __init__(self, delete_raises: Exception | None = None):
        self.deleted: list[tuple] = []
        self._delete_raises = delete_raises

    async def delete(self, *keys):
        self.deleted.append(keys)
        if self._delete_raises is not None:
            raise self._delete_raises
        return len(keys)


def _make_cache(redis) -> CacheService:
    return CacheService(redis_client=redis)


class TestInvalidatePricingKey:
    @pytest.mark.asyncio
    async def test_deletes_the_ppu_svc_key_for_the_service_id(self) -> None:
        redis = _FakeRedis()
        cache = _make_cache(redis)

        await cache.invalidate_pricing("svc-abc")

        assert redis.deleted == [("ppu:svc:svc-abc",)]

    @pytest.mark.asyncio
    async def test_key_matches_payperuse_consumers_prefix_exactly(self) -> None:
        """Cross-service contract: kafka-consumers' payperuse_consumer reads
        Constants.PRICING_CACHE_PREFIX + service_id == "ppu:svc:" + service_id.
        Renaming either side silently stops invalidation from having any
        effect — no error, just a permanently stale cache."""
        redis = _FakeRedis()
        cache = _make_cache(redis)

        await cache.invalidate_pricing("svc-xyz")

        (deleted_key,) = redis.deleted[0]
        assert deleted_key == "ppu:svc:" + "svc-xyz"

    @pytest.mark.asyncio
    async def test_different_service_ids_produce_different_keys(self) -> None:
        redis = _FakeRedis()
        cache = _make_cache(redis)

        await cache.invalidate_pricing("svc-1")
        await cache.invalidate_pricing("svc-2")

        assert redis.deleted == [("ppu:svc:svc-1",), ("ppu:svc:svc-2",)]

    @pytest.mark.asyncio
    async def test_redis_failure_is_swallowed_not_raised(self) -> None:
        """Matches every other cache op in this module: the DB write already
        committed by the time this runs, so a Redis hiccup here must degrade
        to "stale for up to an hour", never fail the whole update request."""
        redis = _FakeRedis(delete_raises=ConnectionError("redis down"))
        cache = _make_cache(redis)

        await cache.invalidate_pricing("svc-abc")  # must not raise

    @pytest.mark.asyncio
    async def test_never_touches_the_service_detail_cache(self) -> None:
        """invalidate_pricing is a distinct, narrower operation from
        invalidate_service (core:service:* — the admin-facing detail cache).
        A caller that means to bust both must call both explicitly."""
        redis = _FakeRedis()
        cache = _make_cache(redis)
        cache.invalidate_service = AsyncMock()  # type: ignore[method-assign]

        await cache.invalidate_pricing("svc-abc")

        cache.invalidate_service.assert_not_called()
