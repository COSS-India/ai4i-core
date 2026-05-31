"""
Shared Redis caching patterns for microservices.

Provides generic key-value helpers on a single Redis connection (logical DB 0).
"""

import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheService:
    """Generic Redis caching operations on one client."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis.setex(key, ttl, value)

    async def get(self, key: str) -> Optional[str]:
        return await self._redis.get(key)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._redis.exists(key) > 0
