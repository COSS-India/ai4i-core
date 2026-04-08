import logging
from typing import Optional

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger("pay-per-use-redis")

_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis():
    global _client
    if _client is not None:
        await _client.close()
        _client = None
