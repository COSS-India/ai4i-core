"""
Shared Redis caching patterns for ALL microservices.

Service-specific cache keys (API key tokens, refresh tokens) stay in
each service. This module provides the generic patterns that every
service needs: role-permission caching and API-permission mapping.
"""

import json
import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_ROLE_PERMS_PREFIX = "auth:role:"
_API_PERMS_KEY = "auth:api_perms"
_ROLE_CACHE_TTL = 3600
_API_PERMS_CACHE_TTL = 3600


class CacheService:
    """Shared Redis caching operations."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    # ── Role → Permission IDs ──

    async def cache_role_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        key = f"{_ROLE_PERMS_PREFIX}{role_id}:perms"
        await self._redis.setex(key, _ROLE_CACHE_TTL, json.dumps(permission_ids))

    async def get_role_permissions(self, role_id: int) -> Optional[list[int]]:
        key = f"{_ROLE_PERMS_PREFIX}{role_id}:perms"
        data = await self._redis.get(key)
        return json.loads(data) if data else None

    async def invalidate_role_cache(self, role_id: int) -> None:
        await self._redis.delete(f"{_ROLE_PERMS_PREFIX}{role_id}:perms")

    # ── API endpoint → Permission mapping ──

    async def cache_api_permission_map(self, mapping: dict[str, str]) -> None:
        await self._redis.setex(_API_PERMS_KEY, _API_PERMS_CACHE_TTL, json.dumps(mapping))

    async def get_api_permission_map(self) -> Optional[dict[str, str]]:
        data = await self._redis.get(_API_PERMS_KEY)
        return json.loads(data) if data else None

    async def get_required_permission(self, method: str, path: str) -> Optional[str]:
        mapping = await self.get_api_permission_map()
        if mapping is None:
            return None
        return mapping.get(f"{method.upper()}:{path}")

    # ── Generic key-value cache ──

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis.setex(key, ttl, value)

    async def get(self, key: str) -> Optional[str]:
        return await self._redis.get(key)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._redis.exists(key) > 0
