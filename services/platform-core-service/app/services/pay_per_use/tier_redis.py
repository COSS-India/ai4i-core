"""Tier status and rate limit in Redis, read by auth-service's /auth/validate.

    core:tier:<tier_id>   HASH   status, rate_limit (absent = no limit), 10-min TTL

Written after every tier commit and rebuilt at startup. A write failure is
logged, not raised: the tier change is already committed, and the TTL bounds
how long auth-service can read the old value before re-reading the DB.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TierStatus
from app.models.pay_per_use.tier import Tier

logger = logging.getLogger(__name__)

KEY_PREFIX = "core:tier:"
TTL_SECONDS = 10 * 60


def _key(tier_id) -> str:
    return f"{KEY_PREFIX}{tier_id}"


def _get_redis():
    """Shared client, or None before ``init_redis`` has run (tests, CLI)."""
    try:
        from app.core.redis import get_redis_client

        return get_redis_client()
    except Exception:
        return None


def _mapping(tier: Tier) -> dict:
    mapping = {"status": TierStatus(tier.status).value}
    if tier.rate_limit is not None:
        mapping["rate_limit"] = str(tier.rate_limit)
    return mapping


def _queue_write(pipe, tier: Tier) -> None:
    # HSET merges, so delete first: a removed rate_limit must not linger. The
    # pipeline is a MULTI, so readers never see the key absent in between.
    pipe.delete(_key(tier.id))
    pipe.hset(_key(tier.id), mapping=_mapping(tier))
    pipe.expire(_key(tier.id), TTL_SECONDS)


async def write_tier(tier: Tier) -> None:
    """Mirror one tier after commit; a DELETED tier's key is removed."""
    redis = _get_redis()
    if redis is None:
        return
    try:
        pipe = redis.pipeline()
        if TierStatus(tier.status) == TierStatus.DELETED:
            pipe.delete(_key(tier.id))
        else:
            _queue_write(pipe, tier)
        await pipe.execute()
    except Exception as exc:
        logger.error("Tier %s Redis write failed; auth-service may enforce a stale state: %s", tier.id, exc)


async def rebuild_all(session: AsyncSession) -> Optional[int]:
    """Rewrite every live tier and remove keys for tiers that are gone."""
    redis = _get_redis()
    if redis is None:
        return None
    result = await session.execute(select(Tier).where(Tier.status != TierStatus.DELETED))
    tiers = list(result.scalars().all())
    live = {_key(t.id) for t in tiers}
    # count=1000: SCAN walks the whole keyspace (lakhs of auth:apikey:* share this
    # Redis), so the default batch of 10 would mean thousands of round trips.
    stale = [k async for k in redis.scan_iter(match=f"{KEY_PREFIX}*", count=1000) if k not in live]

    pipe = redis.pipeline()
    if stale:
        pipe.delete(*stale)
    for tier in tiers:
        _queue_write(pipe, tier)
    await pipe.execute()
    return len(tiers)
