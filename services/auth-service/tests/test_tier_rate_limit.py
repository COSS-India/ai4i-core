"""Tier status and X-Rate-Limit on /auth/validate come from Redis
(core:tier:{tier_id}, written by platform-core); a miss is repaired from the
platform-core DB only if the key is still absent, and a tier unknown to both fails open."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response

from app.routes import validation
from app.services import tier_lookup
from app.services import cache_service
from app.services.cache_service import CacheService


@pytest.mark.asyncio
class TestTierCache:
    async def test_reads_status_and_rate_limit(self):
        redis = MagicMock()
        redis.hmget = AsyncMock(return_value=["ACTIVE", "100"])

        assert await CacheService(redis).get_tier_cache("t1") == ("ACTIVE", 100)
        redis.hmget.assert_awaited_once_with("core:tier:t1", "status", "rate_limit")

    async def test_tier_without_limit(self):
        redis = MagicMock()
        redis.hmget = AsyncMock(return_value=["ACTIVE", None])

        assert await CacheService(redis).get_tier_cache("t1") == ("ACTIVE", None)

    async def test_missing_key_redis_error_or_bad_value_read_as_a_miss(self):
        for hmget in (AsyncMock(return_value=[None, None]), AsyncMock(side_effect=ConnectionError("down")),
                      AsyncMock(return_value=["ACTIVE", "not-a-number"])):
            redis = MagicMock()
            redis.hmget = hmget
            assert await CacheService(redis).get_tier_cache("t1") is None

    async def test_write_back_only_if_key_absent(self):
        redis = MagicMock()
        redis.eval = AsyncMock()

        await CacheService(redis).set_tier_cache("t1", "ACTIVE", 100)
        await CacheService(redis).set_tier_cache("t2", "ACTIVE", None)

        first, second = redis.eval.await_args_list
        assert first.args[0] is cache_service._HSET_IF_KEY_ABSENT
        assert first.args[1:] == (1, "core:tier:t1", 600, "status", "ACTIVE", "rate_limit", "100")
        assert second.args[1:] == (1, "core:tier:t2", 600, "status", "ACTIVE")


def _cache(cached=None) -> MagicMock:
    cache = MagicMock()
    cache.get_tier_cache = AsyncMock(return_value=cached)
    cache.set_tier_cache = AsyncMock()
    return cache


def _factory(row=None, error=None):
    result = MagicMock()
    result.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result, side_effect=error)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


@pytest.mark.asyncio
class TestTierLookup:
    async def test_hit_never_touches_the_db(self, monkeypatch):
        factory = _factory()
        monkeypatch.setattr(tier_lookup, "get_platform_core_session_factory", lambda: factory)
        cache = _cache(("DEACTIVATED", 5))

        assert await tier_lookup.get_tier("t1", cache) == ("DEACTIVATED", 5)
        factory.assert_not_called()
        cache.set_tier_cache.assert_not_awaited()

    async def test_miss_reads_db_and_writes_back(self, monkeypatch):
        monkeypatch.setattr(tier_lookup, "get_platform_core_session_factory", lambda: _factory(("ACTIVE", 100)))
        cache = _cache()

        assert await tier_lookup.get_tier("t1", cache) == ("ACTIVE", 100)
        cache.set_tier_cache.assert_awaited_once_with("t1", "ACTIVE", 100)

    async def test_unknown_tier_fails_open_and_is_not_cached(self, monkeypatch):
        monkeypatch.setattr(tier_lookup, "get_platform_core_session_factory", lambda: _factory(None))
        cache = _cache()

        assert await tier_lookup.get_tier("t1", cache) == (None, None)
        cache.set_tier_cache.assert_not_awaited()

    async def test_db_error_fails_open(self, monkeypatch):
        monkeypatch.setattr(tier_lookup, "get_platform_core_session_factory",
                            lambda: _factory(error=ConnectionError("db down")))

        assert await tier_lookup.get_tier("t1", _cache()) == (None, None)

    async def test_db_not_configured_fails_open(self, monkeypatch):
        monkeypatch.setattr(tier_lookup, "get_platform_core_session_factory", lambda: None)

        assert await tier_lookup.get_tier("t1", _cache()) == (None, None)


def _request() -> MagicMock:
    request = MagicMock()
    request.headers = {}
    return request


@pytest.mark.asyncio
class TestValidateTierFromRedis:
    async def _validate(self, monkeypatch, cache: MagicMock):
        monkeypatch.setattr(tier_lookup, "get_platform_core_session_factory", lambda: None)
        monkeypatch.setattr(validation, "_set_tenant_headers", lambda *_: None)
        api_key_svc = AsyncMock()
        api_key_svc.validate_api_key.return_value = {
            "id": 42, "application_id": "7", "tenant_id": "1", "permissions": [1], "tier_id": "t1",
        }
        response = Response()
        out = await validation._validate_api_key("a" * 32, _request(), response, api_key_svc, cache)
        return out, response

    async def test_rate_limit_header_from_tier(self, monkeypatch):
        out, response = await self._validate(monkeypatch, _cache(("ACTIVE", 100)))
        assert getattr(out, "status_code", 200) == 200
        assert response.headers["X-Rate-Limit"] == "100"

    async def test_no_header_when_tier_has_no_limit(self, monkeypatch):
        _, response = await self._validate(monkeypatch, _cache(("ACTIVE", None)))
        assert "X-Rate-Limit" not in response.headers

    async def test_deactivated_tier_is_rejected(self, monkeypatch):
        out, response = await self._validate(monkeypatch, _cache(("DEACTIVATED", 100)))
        assert out.status_code == 403
        assert b"TIER_DEACTIVATED" in out.body
        assert "X-Rate-Limit" not in response.headers

    async def test_unknown_tier_fails_open(self, monkeypatch):
        out, response = await self._validate(monkeypatch, _cache())
        assert getattr(out, "status_code", 200) == 200
        assert "X-Rate-Limit" not in response.headers
