"""
Cache service for models and services.

Models: stored in Redis with TTL-based invalidation (shared async Redis client).
Services: stored in process-local in-memory dict with 5-minute TTL. Cache misses
are handled by the calling service which falls back to the DB and re-warms
the cache.

Keys:
  core:model:{model_id}:{version}       — model details (Redis)
  core:model:{model_id}                  — latest active version (Redis)
  core:service:{service_id}             — service details (in-memory)
"""

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

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
