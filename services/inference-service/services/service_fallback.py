"""An Application's service fallbacks: {requested service_id: [fallback, ...]}.

auth-service writes the map to Redis as auth:app:{application_id}:service_fallbacks
(no TTL) whenever the Application is saved — the same contract as
auth:app:{id}:policy_ids. A missing key, a request without an Application
(JWT / Try-It) or a Redis failure all mean "no fallback": the request then
fails exactly as it did before this feature.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from ai4i_core.context import get_api_key_id, get_application_id
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


def fallback_span_attrs(requested: str) -> Dict[str, Any]:
    """The "request" span attributes of a request sent to a fallback (the
    requested service was unavailable), whether a fallback answered it or
    every one failed. The billing consumer writes served_by_fallback onto the
    request's usage_events row; requested_service_id stays on the span for
    tracing (service_id there is the fallback that answered, or the requested
    service when none did)."""
    return {"served_by_fallback": True, "requested_service_id": requested}


def mark_sent_to_fallback(request: Optional[Any], requested: str) -> None:
    """Record on request.state that the request was sent to a fallback, so
    the LLM "request" span — opened by the route, outside the fallback chain —
    can carry fallback_span_attrs even when every fallback fails."""
    if request is not None:
        request.state.requested_service_id = requested


def mark_served_by_fallback(request: Optional[Any], requested: str, fallback: str) -> None:
    """Point request.state at the fallback that answered, as well as
    mark_sent_to_fallback."""
    if request is not None:
        request.state.service_id = fallback
        request.state.requested_service_id = requested


def log_failover(requested: str, fallback: str, reason: str) -> None:
    """The failover event the AC asks for: Application, API key, requested and
    fallback service, reason; the timestamp comes from the log record."""
    logger.warning(
        "service_failover application_id=%s api_key_id=%s requested_service_id=%s "
        "fallback_service_id=%s reason=%s",
        get_application_id() or "", get_api_key_id() or "", requested, fallback, reason,
    )


def log_fallback_skipped(requested: str, fallback: str, reason: str) -> None:
    logger.warning(
        "service_fallback_skipped application_id=%s requested_service_id=%s skipped_service_id=%s reason=%s",
        get_application_id() or "", requested, fallback, reason,
    )


def log_all_failed(requested: str, tried: List[str]) -> None:
    logger.error(
        "all_services_failed application_id=%s api_key_id=%s requested_service_id=%s tried=%s",
        get_application_id() or "", get_api_key_id() or "", requested, ",".join(tried),
    )
