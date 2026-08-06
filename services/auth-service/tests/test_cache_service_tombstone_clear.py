"""set_api_key_cache must clear a stale is_already_invalid tombstone when
writing fresh, valid data — HSET is additive and would otherwise leave a
previously-tombstoned key permanently rejecting requests (until the
tombstone's own TTL expires) even after it becomes eligible again and its
cache entry is legitimately refreshed.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.cache_service import REDIS_API_KEY_PREFIX, CacheService


def _redis_with_pipeline():
    """redis.asyncio's pipeline(...) call itself isn't awaited — only the
    context manager's __aenter__/__aexit__ and the yielded pipe's commands
    are. Model that shape explicitly rather than letting AsyncMock's
    auto-async attributes turn `.pipeline(...)` into a coroutine."""
    pipe = AsyncMock()

    @asynccontextmanager
    async def _pipeline(*args, **kwargs):
        yield pipe

    redis = MagicMock()
    redis.pipeline = MagicMock(side_effect=_pipeline)
    return redis, pipe


class TestSetApiKeyCacheClearsStaleTombstone:
    @pytest.mark.asyncio
    async def test_writing_real_data_clears_is_already_invalid(self) -> None:
        redis, pipe = _redis_with_pipeline()
        svc = CacheService(redis)

        await svc.set_api_key_cache("abc123", 3600, {"api_key": "abc123", "permissions": [1]})

        key = f"{REDIS_API_KEY_PREFIX}abc123"
        pipe.hset.assert_awaited_once()
        pipe.hdel.assert_awaited_once_with(key, "is_already_invalid")
        pipe.expire.assert_awaited_once_with(key, 3600)
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_writing_the_tombstone_itself_does_not_self_clear(self) -> None:
        redis, pipe = _redis_with_pipeline()
        svc = CacheService(redis)

        await svc.set_api_key_cache("abc123", 300, {"is_already_invalid": "1"})

        pipe.hset.assert_awaited_once()
        pipe.hdel.assert_not_awaited()
        pipe.expire.assert_awaited_once_with(f"{REDIS_API_KEY_PREFIX}abc123", 300)