"""
Auth-service cache — extends shared CacheService with auth-specific operations.

Generic caching (role permissions, API permission map) comes from shared lib.
Auth-specific caching (API key tokens) is added here.
Refresh tokens are stored in DB only — no Redis caching.
"""

import json
from typing import Optional

import redis.asyncio as aioredis

from ai4icore_bootstrap.cache import CacheService as _BaseCacheService
from app.core.config import settings

# Redis key pattern: auth:apikey:{api_key}
# Defined once here — no other file should construct this key manually.
REDIS_API_KEY_PREFIX = "auth:apikey:"

_ROLE_PERMS_PREFIX = "auth:role:"
_API_PERMS_KEY = "auth:api_perms"
_TENANT_STATUS_PREFIX = "auth:tenant_status:"
_TENANT_USER_STATUS_PREFIX = "auth:tenant_user_status:"
_REVOCATION_COOLDOWN_PREFIX = "auth:revocation_cooldown:"


class CacheService(_BaseCacheService):
    """Extends shared CacheService with auth-specific token caching."""

    def __init__(
        self,
        redis_api_keys: aioredis.Redis,
        redis_role_permissions: aioredis.Redis,
        redis_api_permissions: aioredis.Redis,
    ) -> None:
        super().__init__(redis_api_keys)
        self._redis_api_keys = redis_api_keys
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

    # ── API Key cache (canonical methods) ──

    async def set_api_key_cache(self, api_key: str, ttl_seconds: int, data: dict) -> None:
        """Store api_key metadata in Redis. TTL matches key expiry."""
        await self._redis_api_keys.setex(
            f"{REDIS_API_KEY_PREFIX}{api_key}",
            ttl_seconds,
            json.dumps(data),
        )

    async def get_api_key_cache(self, api_key: str) -> Optional[dict]:
        """Return cached metadata dict, or None on miss/expiry."""
        raw = await self._redis_api_keys.get(f"{REDIS_API_KEY_PREFIX}{api_key}")
        if raw is None:
            return None
        return json.loads(raw)

    async def delete_api_key_cache(self, api_key: str) -> None:
        """Immediately invalidate an API key — used on revocation."""
        await self._redis_api_keys.delete(f"{REDIS_API_KEY_PREFIX}{api_key}")

    # ── Backward-compat aliases (used by dependencies/auth.py) ──

    async def store_api_key_token(self, token_id: str, ttl_seconds: int, metadata: dict | None = None) -> None:
        await self.set_api_key_cache(token_id, ttl_seconds, metadata or {})

    async def is_api_key_valid(self, token_id: str) -> bool:
        return await self.get_api_key_cache(token_id) is not None

    async def revoke_api_key_token(self, token_id: str) -> None:
        await self.delete_api_key_cache(token_id)

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

    async def delete_tenant_status(self, tenant_id: str) -> None:
        tenant_id_norm = (tenant_id or "").strip().lower()
        if not tenant_id_norm:
            return
        await self._redis_api_permissions.delete(f"{_TENANT_STATUS_PREFIX}{tenant_id_norm}")

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

    # ── Revocation endpoint cooldown (anti-DoS guard) ──

    async def acquire_revocation_cooldown(self, scope: str, ttl_seconds: int) -> bool:
        """
        Acquire a short-lived cooldown key.
        Returns True only for the first caller during the cooldown window.
        """
        key = f"{_REVOCATION_COOLDOWN_PREFIX}{scope}"
        result = await self._redis_api_permissions.set(key, "1", ex=ttl_seconds, nx=True)
        return bool(result)

    async def get_revocation_cooldown_ttl(self, scope: str) -> int:
        """Return remaining cooldown in seconds for a scope (0 when absent)."""
        key = f"{_REVOCATION_COOLDOWN_PREFIX}{scope}"
        ttl = await self._redis_api_permissions.ttl(key)
        if ttl is None or ttl < 0:
            return 0
        return int(ttl)
