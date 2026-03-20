"""
Auth-service cache — extends shared CacheService with auth-specific operations.

Generic caching (role permissions, API permission map) comes from shared lib.
Auth-specific caching (API key tokens, refresh tokens) is added here.
"""

import json
from typing import Optional

import redis.asyncio as aioredis

from ai4icore_bootstrap.cache import CacheService as _BaseCacheService
from app.core.config import settings

_API_KEY_PREFIX = "auth:apikey:"
_REFRESH_PREFIX = "auth:refresh:"
_ROLE_PERMS_PREFIX = "auth:role:"
_API_PERMS_KEY = "auth:api_perms"


class CacheService(_BaseCacheService):
    """Extends shared CacheService with auth-specific token caching."""

    # ── Role/API permission caches (env-configurable TTL) ──

    async def cache_role_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        key = f"{_ROLE_PERMS_PREFIX}{role_id}:perms"
        await self._redis.setex(key, settings.role_cache_ttl_seconds, json.dumps(permission_ids))

    async def cache_api_permission_map(self, mapping: dict[str, str]) -> None:
        await self._redis.setex(
            _API_PERMS_KEY,
            settings.api_perms_cache_ttl_seconds,
            json.dumps(mapping),
        )

    # ── API Key token_id ──

    async def store_api_key_token(self, token_id: str, ttl_seconds: int, metadata: dict | None = None) -> None:
        value = json.dumps(metadata) if metadata else "1"
        await self._redis.setex(f"{_API_KEY_PREFIX}{token_id}", ttl_seconds, value)

    async def is_api_key_valid(self, token_id: str) -> bool:
        return await self._redis.exists(f"{_API_KEY_PREFIX}{token_id}") > 0

    async def revoke_api_key_token(self, token_id: str) -> None:
        await self._redis.delete(f"{_API_KEY_PREFIX}{token_id}")

    # ── Refresh token_id ──

    async def store_refresh_token(self, token_id: str, ttl_seconds: int) -> None:
        await self._redis.setex(f"{_REFRESH_PREFIX}{token_id}", ttl_seconds, "1")

    async def is_refresh_token_valid(self, token_id: str) -> bool:
        return await self._redis.exists(f"{_REFRESH_PREFIX}{token_id}") > 0

    async def revoke_refresh_token(self, token_id: str) -> None:
        await self._redis.delete(f"{_REFRESH_PREFIX}{token_id}")
