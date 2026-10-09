"""Redis client for jobs.

Created on first use and closed by the launcher after the job, so a job that
never touches Redis never connects to it:

    redis = get_redis()
    await redis.get(key)
"""
from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis
from ai4i_core.logging import get_logger

from bootstrap.config import get_settings

logger = get_logger(__name__)

_redis_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.get_redis_url(),
            socket_timeout=settings.REDIS_TIMEOUT,
            socket_connect_timeout=settings.REDIS_TIMEOUT,
            decode_responses=True,
        )
        logger.info("Redis client created | host=%s db=%s", settings.REDIS_HOST, settings.REDIS_DB)
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
    _redis_client = None
