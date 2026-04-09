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
_TENANT_STATUS_PREFIX = "auth:tenant_status:"
_TENANT_USER_STATUS_PREFIX = "auth:tenant_user_status:"


class CacheService(_BaseCacheService):
    """Extends shared CacheService with auth-specific token caching."""

    def __init__(
        self,
        redis_api_keys: aioredis.Redis,
        redis_refresh_tokens: aioredis.Redis,
        redis_role_permissions: aioredis.Redis,
        redis_api_permissions: aioredis.Redis,
    ) -> None:
        # Base class still provides generic helpers on the default token cache.
        super().__init__(redis_api_keys)
        self._redis_api_keys = redis_api_keys
        self._redis_refresh_tokens = redis_refresh_tokens
        self._redis_role_permissions = redis_role_permissions
        self._redis_api_permissions = redis_api_permissions

    # ── Role/API permission caches (env-configurable TTL) ──

    async def cache_role_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        key = f"{_ROLE_PERMS_PREFIX}{role_id}:perms"
        await self._redis_role_permissions.setex(key, settings.role_cache_ttl_seconds, json.dumps(permission_ids))

    async def get_role_permissions(self, role_id: int) -> Optional[list[int]]:
        key = f"{_ROLE_PERMS_PREFIX}{role_id}:perms"
        data = await self._redis_role_permissions.get(key)
        return json.loads(data) if data else None

    async def invalidate_role_cache(self, role_id: int) -> None:
        await self._redis_role_permissions.delete(f"{_ROLE_PERMS_PREFIX}{role_id}:perms")

    async def cache_api_permission_map(self, mapping: dict[str, str]) -> None:
        await self._redis_api_permissions.setex(
            _API_PERMS_KEY,
            settings.api_perms_cache_ttl_seconds,
            json.dumps(mapping),
        )

    async def get_api_permission_map(self) -> Optional[dict[str, str]]:
        data = await self._redis_api_permissions.get(_API_PERMS_KEY)
        return json.loads(data) if data else None

    # ── API Key token_id ──

    async def store_api_key_token(self, token_id: str, ttl_seconds: int, metadata: dict | None = None) -> None:
        value = json.dumps(metadata) if metadata else "1"
        await self._redis_api_keys.setex(f"{_API_KEY_PREFIX}{token_id}", ttl_seconds, value)

    async def is_api_key_valid(self, token_id: str) -> bool:
        return await self._redis_api_keys.exists(f"{_API_KEY_PREFIX}{token_id}") > 0

    async def revoke_api_key_token(self, token_id: str) -> None:
        await self._redis_api_keys.delete(f"{_API_KEY_PREFIX}{token_id}")

    # ── Refresh token_id ──

    async def store_refresh_token(self, token_id: str, ttl_seconds: int) -> None:
        await self._redis_refresh_tokens.setex(f"{_REFRESH_PREFIX}{token_id}", ttl_seconds, "1")

    async def is_refresh_token_valid(self, token_id: str) -> bool:
        return await self._redis_refresh_tokens.exists(f"{_REFRESH_PREFIX}{token_id}") > 0

    async def revoke_refresh_token(self, token_id: str) -> None:
        await self._redis_refresh_tokens.delete(f"{_REFRESH_PREFIX}{token_id}")

    # ── Tenant status caches (short TTL for validate path) ──

    async def get_tenant_status(self, tenant_id: str) -> Optional[str]:
        data = await self._redis_api_permissions.get(f"{_TENANT_STATUS_PREFIX}{tenant_id}")
        if not data:
            return None
        if isinstance(data, bytes):
            return data.decode()
        return str(data)

    async def set_tenant_status(self, tenant_id: str, status: str, ttl_seconds: int) -> None:
        await self._redis_api_permissions.setex(
            f"{_TENANT_STATUS_PREFIX}{tenant_id}",
            ttl_seconds,
            status,
        )

    async def get_tenant_user_status(self, tenant_id: str, user_id: int) -> Optional[str]:
        data = await self._redis_api_permissions.get(
            f"{_TENANT_USER_STATUS_PREFIX}{tenant_id}:{user_id}"
        )
        if not data:
            return None
        if isinstance(data, bytes):
            return data.decode()
        return str(data)

    async def set_tenant_user_status(
        self,
        tenant_id: str,
        user_id: int,
        status: str,
        ttl_seconds: int,
    ) -> None:
        await self._redis_api_permissions.setex(
            f"{_TENANT_USER_STATUS_PREFIX}{tenant_id}:{user_id}",
            ttl_seconds,
            status,
        )
