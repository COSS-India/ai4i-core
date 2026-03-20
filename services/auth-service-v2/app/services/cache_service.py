"""
Auth-service cache — extends shared CacheService with auth-specific operations.

Generic caching (role permissions, API permission map) comes from shared lib.
Auth-specific caching (API key tokens, refresh tokens) is added here.
"""

import json
from typing import Optional

import redis.asyncio as aioredis

from ai4icore_bootstrap.cache import CacheService as _BaseCacheService

_API_KEY_PREFIX = "auth:apikey:"
_REFRESH_PREFIX = "auth:refresh:"


class CacheService(_BaseCacheService):
    """Extends shared CacheService with auth-specific token caching."""

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
