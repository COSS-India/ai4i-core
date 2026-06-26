"""
Auth-service cache — extends shared CacheService with auth-specific operations.

Uses a single Redis logical DB; keys are distinguished by prefix.
"""

import json
import logging
from typing import Optional

import redis.asyncio as aioredis
from ai4i_core.bootstrap.cache import CacheService as _BaseCacheService

logger = logging.getLogger(__name__)

# Redis key pattern: auth:apikey:{api_key}
# Defined once here — no other file should construct this key manually.
REDIS_API_KEY_PREFIX = "auth:apikey:"


class CacheService(_BaseCacheService):
    """Extends shared CacheService with auth-specific token caching."""

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)

    async def set_api_key_cache(self, api_key: str, ttl_seconds: int, data: dict) -> None:
        """Store api_key metadata as a Redis hash. TTL set atomically via pipeline."""
        mapping = dict(data)
        if "permissions" in mapping and not isinstance(mapping["permissions"], str):
            mapping["permissions"] = json.dumps(mapping["permissions"])
        mapping = {k: str(v) if v is not None else "" for k, v in mapping.items()}
        key = f"{REDIS_API_KEY_PREFIX}{api_key}"
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.hset(key, mapping=mapping)
            await pipe.expire(key, ttl_seconds)
            await pipe.execute()

    async def get_api_key_cache(self, api_key: str) -> Optional[dict]:
        """Return cached metadata dict, or None on miss/expiry."""
        data = await self._redis.hgetall(f"{REDIS_API_KEY_PREFIX}{api_key}")
        if not data:
            return None
        if "permissions" in data:
            try:
                data["permissions"] = json.loads(data["permissions"])
            except (json.JSONDecodeError, ValueError):
                data["permissions"] = []
        return data

    async def delete_api_key_cache(self, api_key: str) -> None:
        """Immediately invalidate an API key — used on revocation."""
        await self._redis.delete(f"{REDIS_API_KEY_PREFIX}{api_key}")
