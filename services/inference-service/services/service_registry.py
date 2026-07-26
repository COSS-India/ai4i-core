"""Resolve an LLM model name to its registered service_id.

The OpenAI-compatible chat endpoint carries only the ``model`` name, but PPU
billing and metering are keyed on the registered ``service_id`` (a hash stored
in ``mm_services`` that is NOT derivable from the name — see
platform-core ``generate_service_id``; the stored ids predate that formula).

So the id must be read from the registry. This resolver fetches the published
services from the model-management service and maps ``name -> service_id``,
cached with a TTL and refetched on a miss so a newly registered model resolves
without waiting for the TTL to expire. It fails open: if the registry is
unreachable or the model is unknown, it returns "" and the caller proceeds
unbilled rather than failing the request.
"""

import logging
import time
from typing import Dict

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Positive-map freshness. A hit within this window is served from cache.
_CACHE_TTL_SECONDS = 300.0
# Floor between registry fetches, so a burst of requests for an unknown model
# (every one a cache miss) cannot hammer the model-management service.
_MIN_REFRESH_INTERVAL_SECONDS = 10.0


class ServiceIdResolver:
    """Maps a model name to its registered service_id via the MMS, cached."""

    def __init__(self) -> None:
        self._map: Dict[str, str] = {}
        self._fetched_at: float = 0.0
        self._last_attempt_at: float = 0.0
        base = (settings.MODEL_MANAGEMENT_SERVICE_URL or "").strip().rstrip("/")
        # platform-core mounts the model-management API under /api/v1 (see
        # ai4i_core APIVersioning.create_router); mirror release-2.3's resolver.
        self._url = f"{base}/api/v1/services" if base else ""
        self._timeout = float(settings.MODEL_MANAGEMENT_SERVICE_TIMEOUT or 30)

    async def resolve(self, model_name: str) -> str:
        """Return the registered service_id for ``model_name``, or "" if unknown."""
        if not model_name or not self._url:
            return ""

        now = time.monotonic()
        cache_fresh = (now - self._fetched_at) < _CACHE_TTL_SECONDS
        hit = self._map.get(model_name, "")
        if cache_fresh and hit:
            return hit

        # Cache stale, or a miss (the model may have just been registered):
        # refetch, but never more often than the refresh floor.
        if (now - self._last_attempt_at) >= _MIN_REFRESH_INTERVAL_SECONDS:
            await self._refresh()

        return self._map.get(model_name, "")

    async def _refresh(self) -> None:
        self._last_attempt_at = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    self._url,
                    params={"is_published": "true", "limit": 1000},
                )
            resp.raise_for_status()
            services = ((resp.json() or {}).get("data") or {}).get("services") or []
        except Exception as exc:
            # Fail open — keep whatever map we already have; billing degrades to
            # "unbilled" for this call rather than the request failing.
            logger.warning(
                "Service registry fetch failed, service_id resolution degraded: %s", exc
            )
            return

        new_map: Dict[str, str] = {}
        for item in services:
            name = item.get("name")
            service_id = item.get("serviceId") or item.get("service_id")
            if name and service_id:
                new_map[name] = service_id

        self._map = new_map
        self._fetched_at = time.monotonic()
        logger.info(
            "Service registry refreshed: %d published services cached", len(new_map)
        )


# Module-level singleton so the cache is shared across requests (routes create a
# fresh OpenAIProxyService per call).
service_id_resolver = ServiceIdResolver()
