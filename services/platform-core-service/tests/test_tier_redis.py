"""core:tier:{id} in Redis is what auth-service enforces tier status and
rate limit from, so every tier write must land there."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.constants import TierStatus
from app.models.pay_per_use.tier import Tier
from app.services.pay_per_use import tier_redis


def _tier(status=TierStatus.ACTIVE, rate_limit=None) -> Tier:
    t = Tier(id=uuid4(), name="Gold")
    t.status = status
    t.rate_limit = rate_limit
    return t


def _redis(existing_keys=()):
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    redis = MagicMock()
    redis.pipeline.return_value = pipe

    async def scan_iter(match, count=None):
        for k in existing_keys:
            yield k

    redis.scan_iter = scan_iter
    return redis, pipe


@pytest.mark.asyncio
class TestWriteTier:
    async def test_writes_status_and_rate_limit(self, monkeypatch):
        redis, pipe = _redis()
        monkeypatch.setattr(tier_redis, "_get_redis", lambda: redis)
        tier = _tier(rate_limit=100)

        await tier_redis.write_tier(tier)

        key = f"core:tier:{tier.id}"
        pipe.delete.assert_called_once_with(key)
        pipe.hset.assert_called_once_with(key, mapping={"status": "ACTIVE", "rate_limit": "100"})
        pipe.expire.assert_called_once_with(key, 600)
        pipe.execute.assert_awaited_once()

    async def test_no_rate_limit_field_when_unset(self, monkeypatch):
        redis, pipe = _redis()
        monkeypatch.setattr(tier_redis, "_get_redis", lambda: redis)

        await tier_redis.write_tier(_tier(status=TierStatus.DEACTIVATED))

        assert pipe.hset.call_args.kwargs["mapping"] == {"status": "DEACTIVATED"}

    async def test_deleted_tier_removes_key(self, monkeypatch):
        redis, pipe = _redis()
        monkeypatch.setattr(tier_redis, "_get_redis", lambda: redis)
        tier = _tier(status=TierStatus.DELETED)

        await tier_redis.write_tier(tier)

        pipe.delete.assert_called_once_with(f"core:tier:{tier.id}")
        pipe.hset.assert_not_called()

    async def test_redis_failure_does_not_raise(self, monkeypatch):
        redis, pipe = _redis()
        pipe.execute.side_effect = ConnectionError("down")
        monkeypatch.setattr(tier_redis, "_get_redis", lambda: redis)

        await tier_redis.write_tier(_tier())


@pytest.mark.asyncio
class TestRebuildAll:
    async def test_rewrites_live_tiers_and_removes_stale_keys(self, monkeypatch):
        live = _tier(rate_limit=50)
        redis, pipe = _redis(existing_keys=[f"core:tier:{live.id}", "core:tier:gone"])
        monkeypatch.setattr(tier_redis, "_get_redis", lambda: redis)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[live])))))

        count = await tier_redis.rebuild_all(session)

        assert count == 1
        pipe.delete.assert_any_call("core:tier:gone")
        pipe.hset.assert_called_once_with(f"core:tier:{live.id}", mapping={"status": "ACTIVE", "rate_limit": "50"})
