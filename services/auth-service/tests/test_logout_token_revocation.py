"""Unit tests: global-logout access-token revocation.

Covers the two new pieces added for this: CacheService's Redis-backed
logout-timestamp store, and check_token_revocation's use of it for
non-api_key tokens. No real Redis — CacheService is built on an
AsyncMock redis client.
"""
from unittest.mock import AsyncMock

import pytest

from app.dependencies.auth import _check_logout_revocation, check_token_revocation
from app.services.cache_service import REDIS_LOGOUT_PREFIX, CacheService


def _cache_with_redis() -> tuple[CacheService, AsyncMock]:
    redis = AsyncMock()
    return CacheService(redis), redis


@pytest.mark.asyncio
class TestCacheServiceLogoutTimestamp:
    async def test_set_logout_timestamp_writes_setex_with_ttl(self):
        cache, redis = _cache_with_redis()
        await cache.set_logout_timestamp("user-1", ttl_seconds=3600)

        args, _ = redis.setex.call_args
        key, ttl, value = args
        assert key == f"{REDIS_LOGOUT_PREFIX}user-1"
        assert ttl == 3600
        assert float(value) > 0

    async def test_get_logout_timestamp_returns_stored_value(self):
        cache, redis = _cache_with_redis()
        redis.get.return_value = "1700000000.5"

        result = await cache.get_logout_timestamp("user-1")

        redis.get.assert_awaited_once_with(f"{REDIS_LOGOUT_PREFIX}user-1")
        assert result == 1700000000.5

    async def test_get_logout_timestamp_returns_none_on_miss(self):
        cache, redis = _cache_with_redis()
        redis.get.return_value = None

        assert await cache.get_logout_timestamp("user-1") is None


@pytest.mark.asyncio
class TestCheckLogoutRevocation:
    async def test_token_issued_before_logout_is_revoked(self):
        cache, redis = _cache_with_redis()
        redis.get.return_value = "1700000100.0"  # logged out at t=100

        revoked = await _check_logout_revocation("user-1", issued_at=1700000000.0, cache_service=cache)
        assert revoked is True

    async def test_token_issued_after_logout_is_not_revoked(self):
        cache, redis = _cache_with_redis()
        redis.get.return_value = "1700000000.0"  # logged out at t=0

        revoked = await _check_logout_revocation("user-1", issued_at=1700000100.0, cache_service=cache)
        assert revoked is False

    async def test_no_logout_recorded_is_not_revoked(self):
        cache, redis = _cache_with_redis()
        redis.get.return_value = None

        revoked = await _check_logout_revocation("user-1", issued_at=1700000000.0, cache_service=cache)
        assert revoked is False


@pytest.mark.asyncio
class TestCheckTokenRevocationDispatch:
    async def test_access_token_checks_logout_timestamp_when_user_context_given(self):
        cache, redis = _cache_with_redis()
        redis.get.return_value = "1700000100.0"

        revoked = await check_token_revocation(
            "jti-1", "access_token", cache,
            user_id="user-1", issued_at=1700000000.0,
        )
        assert revoked is True
        redis.get.assert_awaited_once_with(f"{REDIS_LOGOUT_PREFIX}user-1")

    async def test_access_token_without_user_context_is_not_revoked(self):
        """Old callers that don't pass user_id/issued_at keep prior behaviour."""
        cache, redis = _cache_with_redis()

        revoked = await check_token_revocation("jti-1", "access_token", cache)

        assert revoked is False
        redis.get.assert_not_awaited()

    async def test_api_key_still_uses_api_key_cache_not_logout_timestamp(self):
        cache, redis = _cache_with_redis()
        redis.hgetall.return_value = {}  # cache miss => revoked

        revoked = await check_token_revocation(
            "key-1", "api_key", cache,
            user_id="user-1", issued_at=1700000000.0,
        )

        assert revoked is True
        redis.get.assert_not_awaited()  # never consults the logout timestamp
