"""An Application's service fallbacks: {requested service_id: [fallback, ...]}.

auth-service writes the map to Redis as auth:app:{application_id}:service_fallbacks
(no TTL) whenever the Application is saved — the same contract as
auth:app:{id}:policy_ids. A missing key, a request without an Application
(JWT / Try-It) or a Redis failure all mean "no fallback": the request then
fails exactly as it did before this feature.
"""

import json
import logging
from typing import List, Optional

import redis.asyncio as aioredis

from ai4i_core.context import get_application_id
from config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            socket_timeout=settings.REDIS_TIMEOUT,
            # Read only on the failure path: a Redis outage must not add
            # REDIS_TIMEOUT to every failed request before its 502.
            socket_connect_timeout=2,
            decode_responses=True,
        )
    return _redis


async def get_fallbacks(service_id: str) -> List[str]:
    """Ordered fallback service ids for ``service_id`` under the current
    request's Application; [] when there are none or they can't be read."""
    app_id = get_application_id()
    if not app_id or not service_id:
        return []
    try:
        raw = await _get_redis().get(f"auth:app:{app_id}:service_fallbacks")
        fallbacks = (json.loads(raw) if raw else {}).get(service_id) or []
    except Exception as exc:
        logger.warning("Service fallback lookup failed for app_id=%s: %s", app_id, type(exc).__name__)
        return []
    return [str(f) for f in fallbacks if f and f != service_id]
