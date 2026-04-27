"""
Cache service for models and services.

Stores serialized JSON in Redis with TTL-based invalidation. Cache misses
are handled by the calling service which falls back to the DB and re-warms
the cache. We deliberately avoid the redis-om HashModel approach used by the
old model-management-service because it ties our schema to a specific cache
serialization format and uses a sync Redis client; here we use the platform's
shared async Redis client instead.

Keys:
  core:model:{model_id}:{version}       — model details
  core:model:{model_id}                  — latest active version (default lookup)
  core:service:{service_id}             — service details

All values are JSON-encoded.
"""

import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheService:
    """Async Redis-backed cache for models and services."""

    _MODEL_KEY = "core:model"
    _SERVICE_KEY = "core:service"

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

    async def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        try:
            raw = await self._redis.get(self._service_key(service_id))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("Service cache read failed for %s: %s", service_id, exc)
            return None

    async def set_service(self, service_id: str, data: Dict[str, Any]) -> None:
        try:
            payload = json.dumps(data, default=str)
            await self._redis.setex(
                self._service_key(service_id), self._service_ttl, payload
            )
        except Exception as exc:
            logger.warning("Service cache write failed for %s: %s", service_id, exc)

    async def invalidate_service(self, service_id: str) -> None:
        try:
            await self._redis.delete(self._service_key(service_id))
        except Exception as exc:
            logger.warning("Service cache invalidation failed for %s: %s", service_id, exc)
