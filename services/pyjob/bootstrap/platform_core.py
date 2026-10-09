"""Client for platform-core's internal endpoints.

Jobs only trigger work; the work itself (partition DDL, rollups, checks) runs
in platform-core behind ``_require_internal_caller``, which also holds the
advisory locks that keep overlapping runs from racing.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx
from ai4i_core.logging import get_logger

from bootstrap.config import get_settings

logger = get_logger(__name__)


async def call_internal(path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """POST ``payload`` to ``/internal/<path>`` and return the JSON body.

    Raises on a non-2xx response so the job exits as failed.
    """
    settings = get_settings()
    if not settings.PLATFORM_CORE_SERVICE_URL or not settings.INTERNAL_SERVICE_SHARED_SECRET:
        raise RuntimeError("PLATFORM_CORE_SERVICE_URL and INTERNAL_SERVICE_SHARED_SECRET must be set")
    url = f"{settings.PLATFORM_CORE_SERVICE_URL.rstrip('/')}/internal/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=settings.INTERNAL_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url,
            json=payload or {},
            headers={"X-Internal-Service-Token": settings.INTERNAL_SERVICE_SHARED_SECRET},
        )
    response.raise_for_status()
    body = response.json() if response.content else {}
    logger.info("Internal call succeeded | path=%s status=%s", path, response.status_code)
    return body
