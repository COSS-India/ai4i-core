"""Application service-fallback config: which services to try, in order,
when the requested one is unreachable.

The map ``{service_id: [fallback_1, fallback_2, ...]}`` is set on the
Application in auth-service, which writes it to Redis as
``auth:app:{application_id}:service_fallbacks`` (no TTL). Lookup order:

  1. Redis — through the guardrail's client, the same one that reads
     ``auth:app:{id}:policy_ids``;
  2. on a miss (or Redis down), auth-service's internal route, which reloads
     the map from Postgres and writes the key back.

It's only looked up after the requested service has failed over, so a
healthy request never reads it.

Any failure along the way means "no fallback" — the request then runs exactly
as it did before this feature. Requests with no Application id (JWT / Try-It)
never get a fallback.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

import httpx

from ai4i_core.context import get_api_key_id, get_application_id
from config import settings
from services import guardrail

logger = logging.getLogger(__name__)

_FALLBACKS_KEY = "auth:app:{}:service_fallbacks"
_AUTH_LOOKUP_TIMEOUT_SECONDS = 3.0

async def _read_redis(app_id: str) -> Optional[Dict[str, List[str]]]:
    # The guardrail's client, called through the module so a test that
    # patches guardrail._get_redis covers this read too.
    redis = guardrail._get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(_FALLBACKS_KEY.format(app_id))
    except Exception as exc:
        logger.warning("Service fallback: Redis read failed for app_id=%s: %s", app_id, type(exc).__name__)
        return None
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        logger.warning("Service fallback: unreadable Redis value for app_id=%s", app_id)
        return None
    return value if isinstance(value, dict) else None


async def _read_auth_service(app_id: str) -> Dict[str, List[str]]:
    if not settings.AUTH_SERVICE_URL:
        logger.warning("Service fallback: config missing for app_id=%s and AUTH_SERVICE_URL is unset", app_id)
        return {}
    url = f"{settings.AUTH_SERVICE_URL.rstrip('/')}/internal/applications/{app_id}/service-fallbacks"
    try:
        async with httpx.AsyncClient(timeout=_AUTH_LOOKUP_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
        response.raise_for_status()
        value = (response.json() or {}).get("service_fallbacks") or {}
    except Exception as exc:
        logger.warning("Service fallback: auth-service lookup failed for app_id=%s: %s", app_id, type(exc).__name__)
        return {}
    return value if isinstance(value, dict) else {}


async def get_fallbacks(service_id: str, app_id: Optional[str] = None) -> List[str]:
    """Ordered fallback service ids for ``service_id`` under the current
    request's Application; [] when there are none or they can't be read."""
    app_id = app_id if app_id is not None else get_application_id()
    if not app_id or not service_id:
        return []

    mapping = await _read_redis(app_id)
    if mapping is None:
        mapping = await _read_auth_service(app_id)

    fallbacks = mapping.get(service_id) or []
    return [str(f) for f in fallbacks if f and f != service_id]


def log_failover(
    *, requested: str, failed: str, next_service: str, reason: str, attempt: int
) -> None:
    """The failover event the Jira asks for: key, Application, services,
    reason; the timestamp comes from the log record."""
    logger.warning(
        "service_failover requested_service_id=%s failed_service_id=%s fallback_service_id=%s "
        "reason=%s attempt=%d application_id=%s api_key_id=%s",
        requested, failed, next_service, reason, attempt,
        get_application_id() or "", get_api_key_id() or "",
    )


def log_fallback_skipped(*, requested: str, skipped: str, reason: str) -> None:
    logger.warning(
        "service_fallback_skipped requested_service_id=%s skipped_service_id=%s reason=%s application_id=%s",
        requested, skipped, reason, get_application_id() or "",
    )


def log_all_failed(*, requested: str, attempts: List[Tuple[str, str]]) -> None:
    logger.error(
        "all_services_failed requested_service_id=%s attempted=%s application_id=%s api_key_id=%s",
        requested, ",".join(f"{sid}:{reason}" for sid, reason in attempts),
        get_application_id() or "", get_api_key_id() or "",
    )
