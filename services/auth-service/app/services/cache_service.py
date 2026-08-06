"""
Auth-service cache — extends shared CacheService with auth-specific operations.

Uses a single Redis logical DB; keys are distinguished by prefix.
"""

import json
import logging
import time
from typing import Optional

import redis.asyncio as aioredis
from redis.exceptions import ResponseError
from ai4i_core.bootstrap.cache import CacheService as _BaseCacheService

logger = logging.getLogger(__name__)

# Redis key pattern: auth:apikey:{api_key}
# Defined once here — no other file should construct this key manually.
REDIS_API_KEY_PREFIX = "auth:apikey:"

# Redis key pattern: auth:logout:{user_id} -> unix timestamp of last logout.
# Access tokens issued before this timestamp are considered revoked.
REDIS_LOGOUT_PREFIX = "auth:logout:"


class CacheService(_BaseCacheService):
    """Extends shared CacheService with auth-specific token caching."""

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)

    async def set_api_key_cache(self, api_key: str, ttl_seconds: int, data: dict) -> None:
        """Store api_key metadata as a Redis hash. TTL set atomically via pipeline.

        HSET is additive — it never clears a field just because ``data`` omits it. Every
        caller here is writing a fresh, valid payload, which is incompatible with a
        leftover is_already_invalid="1" tombstone from a prior miss, so that field is
        explicitly cleared too, unless ``data`` itself is the tombstone write.
        """
        mapping = dict(data)
        if "permissions" in mapping and not isinstance(mapping["permissions"], str):
            mapping["permissions"] = json.dumps(mapping["permissions"])
        mapping = {k: str(v) if v is not None else "" for k, v in mapping.items()}
        key = f"{REDIS_API_KEY_PREFIX}{api_key}"
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.hset(key, mapping=mapping)
            if "is_already_invalid" not in mapping:
                await pipe.hdel(key, "is_already_invalid")
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

    async def set_logout_timestamp(self, user_id: str, ttl_seconds: int) -> None:
        """Record a global logout for user_id. Tokens with iat before this are revoked.

        TTL matches the access-token lifetime — once it elapses, any token
        issued before the logout has expired on its own anyway.
        """
        await self._redis.setex(f"{REDIS_LOGOUT_PREFIX}{user_id}", ttl_seconds, str(time.time()))

    async def get_logout_timestamp(self, user_id: str) -> Optional[float]:
        """Return the unix timestamp of the user's last logout, or None if none/expired."""
        value = await self._redis.get(f"{REDIS_LOGOUT_PREFIX}{user_id}")
        return float(value) if value else None

    async def patch_api_key_cache_field(self, api_key: str, field: str, value: str) -> bool:
        """Update a single field on an existing API key hash. No-op if key is absent from Redis."""
        key = f"{REDIS_API_KEY_PREFIX}{api_key}"
        if await self._redis.exists(key):
            try:
                await self._redis.hset(key, field, value)
            except ResponseError:
                logger.warning("Skipping HSET on non-hash key %s — stale/legacy data, deleting", key)
                await self._redis.delete(key)
                return False
            return True
        return False

    async def delete_api_key_cache_field(self, api_key: str, field: str) -> None:
        """Remove a single field from an existing API key hash (e.g. quota-* on month rollover)."""
        key = f"{REDIS_API_KEY_PREFIX}{api_key}"
        try:
            await self._redis.hdel(key, field)
        except ResponseError:
            logger.warning("Skipping HDEL on non-hash key %s — stale/legacy data, deleting", key)
            await self._redis.delete(key)

    async def delete_api_key_cache_fields(self, api_key: str, fields: list[str]) -> None:
        """Remove multiple fields from an API key hash in a single HDEL call."""
        if fields:
            key = f"{REDIS_API_KEY_PREFIX}{api_key}"
            try:
                await self._redis.hdel(key, *fields)
            except ResponseError:
                logger.warning("Skipping HDEL on non-hash key %s — stale/legacy data, deleting", key)
                await self._redis.delete(key)

    async def delete_api_key_cache_fields_bulk(
        self, api_keys: list[str], fields: list[str], *, chunk_size: int = 5
    ) -> None:
        """Same as delete_api_key_cache_fields but across many keys, pipelined
        in chunks instead of one HDEL round-trip per key. Used when an
        operation needs to clear the same fields for many API keys at once
        (e.g. the monthly quota-reset cron) — HDEL is idempotent, so if a
        chunk fails partway through it's safe to just retry the whole call."""
        if not fields or not api_keys:
            return
        for start in range(0, len(api_keys), chunk_size):
            chunk = api_keys[start : start + chunk_size]
            try:
                async with self._redis.pipeline(transaction=False) as pipe:
                    for api_key in chunk:
                        pipe.hdel(f"{REDIS_API_KEY_PREFIX}{api_key}", *fields)
                    await pipe.execute()
            except ResponseError:
                # A non-hash (stale/legacy) key in this chunk failed its HDEL — the
                # pipeline aborts that command but others in the chunk still applied.
                # Fall back to the single-key path for this chunk so each key gets
                # its own error handling (delete-if-non-hash) instead of silently
                # skipping the whole chunk.
                logger.warning(
                    "Bulk HDEL chunk hit a non-hash key — retrying chunk one key at a time"
                )
                for api_key in chunk:
                    await self.delete_api_key_cache_fields(api_key, fields)
