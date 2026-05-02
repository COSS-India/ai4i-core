"""
Auth-service cache — extends shared CacheService with auth-specific operations.

Uses a single Redis logical DB; keys are distinguished by prefix.
"""

import json
from typing import Optional

import redis.asyncio as aioredis

from ai4icore_bootstrap.cache import CacheService as _BaseCacheService

# Redis key pattern: auth:apikey:{api_key}
# Defined once here — no other file should construct this key manually.
REDIS_API_KEY_PREFIX = "auth:apikey:"


class CacheService(_BaseCacheService):
    """Extends shared CacheService with auth-specific token caching."""

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)

    async def set_api_key_cache(self, api_key: str, ttl_seconds: int, data: dict) -> None:
        """Store api_key metadata in Redis. TTL matches key expiry."""
        await self._redis.setex(
            f"{REDIS_API_KEY_PREFIX}{api_key}",
            ttl_seconds,
            json.dumps(data),
        )

    async def get_api_key_cache(self, api_key: str) -> Optional[dict]:
        """Return cached metadata dict, or None on miss/expiry."""
        raw = await self._redis.get(f"{REDIS_API_KEY_PREFIX}{api_key}")
        if raw is None:
            return None
        return json.loads(raw)

    async def delete_api_key_cache(self, api_key: str) -> None:
        """Immediately invalidate an API key — used on revocation."""
        await self._redis.delete(f"{REDIS_API_KEY_PREFIX}{api_key}")

