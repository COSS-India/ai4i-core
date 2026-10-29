"""
Cache service for models and services.

Models: stored in Redis with TTL-based invalidation (shared async Redis client).
Services: stored in process-local in-memory dict with 5-minute TTL. Cache misses
are handled by the calling service which falls back to the DB and re-warms
the cache.

Keys (note the encoding — mixing up GET and HGETALL is a WRONGTYPE error):
  core:model:{model_id}:{version}       — model details (Redis STRING, use GET)
  core:model:{model_id}                  — latest active version (Redis STRING, use GET)
  core:service:{service_id}             — service details (in-memory)
  core:service:{service_id}:access      — {"is_published", "tier_ids"} (Redis STRING, use GET)
Written when a service is created, updated or deleted (see set_service_access),
not on reads: a read could write back a row loaded just before an unpublish.
Read by inference-service's resolver on every resolve, so an unpublish or Tier
change reaches every inference pod at once instead of after its in-memory TTL;
with no key, inference keeps its cached flags.

Owned elsewhere, listed here so the namespace stays legible:
  core:inference_type:{name}            — one catalogue row (Redis HASH, use HGETALL)
  core:inference_type:all               — name -> row JSON (Redis HASH, use HGETALL/HGET)
Written by app/services/pay_per_use/inference_type_cache.py, which is their only
writer. Read by kafka-consumers' payperuse_consumer (HGET of the id field) and by
ai4i_core.ppu.catalogue in auth-service and inference-service. Every reader has a
database fallback — see inference_type_cache.py's docstring.

  ppu:svc:{service_id}                  — pricing (task_type, unit_rate,
                                           cost_per_unit, unit_size) (Redis HASH)
Written and read by kafka-consumers' payperuse_consumer._billing.get_service_pricing,
which populates it lazily on a cache miss with a 1-hour TTL. This module is not a
writer, only an invalidator: invalidate_pricing() below deletes the key so the next
billing event re-reads mm_services instead of a stale rate for up to an hour. Safe to
delete blind — the consumer's read path always falls back to the DB and re-warms.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheService:
    """Cache for models (Redis) and services (in-memory, 5-minute TTL)."""

    _MODEL_KEY = "core:model"
    _SERVICE_KEY = "core:service"

    # In-memory store for service cache: key → (data, expires_at)
    _service_store: Dict[str, Tuple[Dict[str, Any], float]] = {}

    def __init__(
        self,
        redis_client: aioredis.Redis,
        *,
        model_ttl_seconds: int = 3600,
        service_ttl_seconds: int = 3600,
    ) -> None:
        self._redis = redis_client
        self._model_ttl = model_ttl_seconds
        self._service_ttl = service_ttl_seconds

    # ── Model cache ──

    @classmethod
    def _model_key(cls, model_id: str, version: Optional[str] = None) -> str:
        if version:
            return f"{cls._MODEL_KEY}:{model_id}:{version}"
        return f"{cls._MODEL_KEY}:{model_id}"

    async def get_model(
        self, model_id: str, version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            raw = await self._redis.get(self._model_key(model_id, version))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("Model cache read failed for %s: %s", model_id, exc)
            return None

    async def set_model(
        self,
        model_id: str,
        version: str,
        data: Dict[str, Any],
        *,
        is_default_version: bool = False,
    ) -> None:
        """Cache the (model_id, version) entry. If is_default_version, also
        cache it under the bare model_id key for "latest active" lookups."""
        try:
            payload = json.dumps(data, default=str)
            await self._redis.setex(
                self._model_key(model_id, version), self._model_ttl, payload
            )
            if is_default_version:
                await self._redis.setex(
                    self._model_key(model_id), self._model_ttl, payload
                )
        except Exception as exc:
            logger.warning("Model cache write failed for %s: %s", model_id, exc)

    async def invalidate_model(
        self, model_id: str, version: Optional[str] = None
    ) -> None:
        try:
            keys = [self._model_key(model_id)]
            if version:
                keys.append(self._model_key(model_id, version))
            await self._redis.delete(*keys)
        except Exception as exc:
            logger.warning("Model cache invalidation failed for %s: %s", model_id, exc)

    async def invalidate_all_versions(self, model_id: str) -> None:
        """Wipe every cached version for a model_id (use after deletes)."""
        try:
            pattern = f"{self._MODEL_KEY}:{model_id}*"
            async for key in self._redis.scan_iter(match=pattern):
                await self._redis.delete(key)
        except Exception as exc:
            logger.warning("Model cache wipe failed for %s: %s", model_id, exc)

    # ── Service cache ──

    @classmethod
    def _service_key(cls, service_id: str) -> str:
        return f"{cls._SERVICE_KEY}:{service_id}"

    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        try:
            entry = CacheService._service_store.get(self._service_key(service_id))
            if entry is None:
                return None
            data, expires_at = entry
            if time.time() > expires_at:
                CacheService._service_store.pop(self._service_key(service_id), None)
                return None
            return data
        except Exception as exc:
            logger.warning("Service cache read failed for %s: %s", service_id, exc)
            return None

    def set_service(self, service_id: str, data: Dict[str, Any]) -> None:
        try:
            CacheService._service_store[self._service_key(service_id)] = (
                data,
                time.time() + self._service_ttl,
            )
        except Exception as exc:
            logger.warning("Service cache write failed for %s: %s", service_id, exc)

    def invalidate_service(self, service_id: str) -> None:
        try:
            CacheService._service_store.pop(self._service_key(service_id), None)
        except Exception as exc:
            logger.warning("Service cache invalidation failed for %s: %s", service_id, exc)

    # ── Service access (Redis, read by inference-service) ──

    # Must outlive inference-service's in-memory resolver TTL (CACHE_TTL_SECONDS,
    # 300 s) and this cache's own (SERVICE_CACHE_TTL_SECONDS): inference falls
    # back to its cached copy when the key is gone, and by then that copy was
    # fetched after the last write.
    _SERVICE_ACCESS_TTL_SECONDS = 3600

    @classmethod
    def _service_access_key(cls, service_id: str) -> str:
        return f"{cls._SERVICE_KEY}:{service_id}:access"

    async def set_service_access(
        self, service_id: str, is_published: bool, tier_ids: Optional[List[str]]
    ) -> None:
        """Publish whether ``service_id`` may be called, and by which Tiers."""
        try:
            await self._redis.setex(
                self._service_access_key(service_id),
                self._SERVICE_ACCESS_TTL_SECONDS,
                json.dumps({"is_published": bool(is_published), "tier_ids": [str(t) for t in tier_ids or []]}),
            )
        except Exception as exc:
            logger.warning("Service access cache write failed for %s: %s", service_id, exc)

    # ── Pricing cache (owned by payperuse_consumer; see module docstring) ──

    _PRICING_KEY = "ppu:svc"

    async def invalidate_pricing(self, service_id: str) -> None:
        """Delete payperuse_consumer's cached pricing for service_id.

        Call this whenever an update changes cost_per_unit,
        cached_input_cost_per_unit, output_cost_per_unit, unit_size,
        unit_rate, or task_type, so the price change takes effect on the
        very next billing event instead of waiting out the 1-hour TTL.
        """
        try:
            await self._redis.delete(f"{self._PRICING_KEY}:{service_id}")
        except Exception as exc:
            logger.warning("Pricing cache invalidation failed for %s: %s", service_id, exc)
