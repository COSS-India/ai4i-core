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

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis key pattern: auth:apikey:{api_key}
# Defined once here — no other file should construct this key manually.
REDIS_API_KEY_PREFIX = "auth:apikey:"

# Redis key pattern: auth:logout:{user_id} -> unix timestamp of last logout.
# Access tokens issued before this timestamp are considered revoked.
REDIS_LOGOUT_PREFIX = "auth:logout:"

# Redis key pattern: core:tier:{tier_id} -> HASH status, rate_limit (absent = no limit).
# Written by platform-core (tier_redis.py); auth only repairs a missing key.
REDIS_TIER_PREFIX = "core:tier:"

# HSET only when the field already exists on the hash — one atomic step, so
# a hash evicted between the check and the write is never recreated as a
# partial, TTL-less entry. Returns 1 if written, 0 otherwise.
_HSET_IF_FIELD_EXISTS = """
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 1 then
  redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
  return 1
end
return 0
"""

# HSET only when the key does not exist yet — hashes have no whole-key NX.
_HSET_IF_KEY_ABSENT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
  redis.call('HSET', KEYS[1], unpack(ARGV))
  return 1
end
return 0
"""


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

    async def get_tier_cache(self, tier_id: str) -> Optional[tuple[str, Optional[int]]]:
        """``(status, rate_limit)``, or None on a miss, Redis error or bad value."""
        try:
            status, rate_limit = await self._redis.hmget(f"{REDIS_TIER_PREFIX}{tier_id}", "status", "rate_limit")
            if status is None:
                return None
            return status, int(rate_limit) if rate_limit is not None else None
        except Exception as exc:
            logger.warning("Tier %s Redis read failed: %s", tier_id, exc)
            return None

    async def set_tier_cache(self, tier_id: str, status: str, rate_limit: Optional[int]) -> None:
        """Write back a tier read from the DB, only if the key is still absent,
        so it never overwrites platform-core. Best-effort."""
        fields = ["status", status]
        if rate_limit is not None:
            fields += ["rate_limit", str(rate_limit)]
        try:
            await self._redis.eval(_HSET_IF_KEY_ABSENT, 1, f"{REDIS_TIER_PREFIX}{tier_id}", *fields)
        except Exception as exc:
            logger.warning("Tier %s Redis write-back failed: %s", tier_id, exc)

    async def delete_api_key_cache(self, api_key: str) -> None:
        """Immediately invalidate an API key — used on revocation."""
        await self._redis.delete(f"{REDIS_API_KEY_PREFIX}{api_key}")

    async def set_logout_timestamp(self, user_id: str, ttl_seconds: int) -> None:
        """Record a global logout for user_id. Tokens with iat before this are revoked.

        TTL matches the access-token lifetime — once it elapses, any token
        issued before the logout has expired on its own anyway.
        """
        await self._redis.setex(f"{REDIS_LOGOUT_PREFIX}{user_id}", ttl_seconds, str(int(time.time())))

    async def revoke_all_sessions(self, user_id: str) -> None:
        """Reject any access token already issued for user_id, using the
        access-token lifetime as TTL (see set_logout_timestamp)."""
        await self.set_logout_timestamp(
            user_id, ttl_seconds=settings.access_token_expire_minutes * 60
        )

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

    async def patch_api_key_cache_field_if_present(
        self, api_key: str, field: str, value: str
    ) -> bool:
        """Like patch_api_key_cache_field, but only overwrites ``field`` when
        the hash already has it — a hash without the field is left exactly
        as it is. Returns True only when the field was written."""
        key = f"{REDIS_API_KEY_PREFIX}{api_key}"
        try:
            return bool(await self._redis.eval(_HSET_IF_FIELD_EXISTS, 1, key, field, value))
        except ResponseError:
            logger.warning("Skipping HSET on non-hash key %s — stale/legacy data, deleting", key)
            await self._redis.delete(key)
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
