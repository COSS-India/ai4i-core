"""
Upstream profiler API client.

Wraps the external profiler HTTP call.  The caller passes only the raw
text; this module builds the full upstream payload, fires the request,
and returns the verbatim JSON response so the rest of the service
stays decoupled from upstream API details.

Environment variable:
  PROFILER_API_URL – full URL of the upstream profiler endpoint.
                     e.g. http://13.201.140.42:8000/api/v1/profile
"""

import logging
import os
from typing import Any, Dict

import httpx
from fastapi import HTTPException

try:
    from ai4icore_logging import get_logger

    logger = get_logger(__name__)
except Exception:  # pragma: no cover – fallback when lib not installed
    logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration – loaded once at module import time
# ---------------------------------------------------------------------------
PROFILER_API_URL: str = os.getenv("PROFILER_API_URL", "")

# Default options forwarded to the upstream API.
# These match the upstream API contract and can be extended via env vars
# in future iterations without touching callers.
_DEFAULT_OPTIONS: Dict[str, bool] = {
    "include_entities": False,
    "include_language_detection": False,
}
_DEFAULT_SOURCE_LANG: str = os.getenv("PROFILER_SOURCE_LANG", "en")

# HTTP timeout for upstream calls (seconds)
_REQUEST_TIMEOUT: float = float(os.getenv("PROFILER_REQUEST_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def call_profiler_api(text: str) -> Dict[str, Any]:
    """Forward ``text`` to the upstream profiler API and return its response.

    Args:
        text: The input text to profile.

    Returns:
        The verbatim JSON response body from the upstream profiler API.

    Raises:
        HTTPException 500 – PROFILER_API_URL not configured.
        HTTPException 5xx – Upstream returned a non-2xx status.
        HTTPException 503 – Could not reach the upstream API.
    """
    if not PROFILER_API_URL:
        logger.error(
            "PROFILER_API_URL is not set; cannot call upstream profiler",
            extra={"context": {"env_var": "PROFILER_API_URL"}},
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PROFILER_API_URL_NOT_SET",
                "message": (
                    "PROFILER_API_URL environment variable is not configured. "
                    "Set it to the upstream profiler endpoint URL."
                ),
            },
        )

    payload: Dict[str, Any] = {
        "options": _DEFAULT_OPTIONS,
        "source_lang": _DEFAULT_SOURCE_LANG,
        "text": text,
    }

    logger.info(
        "Calling upstream profiler API",
        extra={
            "context": {
                "url": PROFILER_API_URL,
                "text_length": len(text),
                "source_lang": _DEFAULT_SOURCE_LANG,
            }
        },
    )

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                PROFILER_API_URL,
                json=payload,
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            result: Dict[str, Any] = response.json()

        logger.info(
            "Upstream profiler API responded successfully",
            extra={
                "context": {
                    "status_code": response.status_code,
                    "response_keys": list(result.keys()) if isinstance(result, dict) else None,
                }
            },
        )
        return result

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Upstream profiler API returned a non-2xx status",
            extra={
                "context": {
                    "status_code": exc.response.status_code,
                    "response_text": exc.response.text[:500] if exc.response else None,
                    "url": PROFILER_API_URL,
                }
            },
        )
        raise HTTPException(
            status_code=exc.response.status_code if exc.response else 500,
            detail={
                "code": "UPSTREAM_PROFILER_ERROR",
                "message": (
                    f"Upstream profiler API returned an error: "
                    f"{exc.response.text[:200] if exc.response else str(exc)}"
                ),
            },
        )

    except httpx.RequestError as exc:
        logger.error(
            "Failed to connect to upstream profiler API",
            extra={
                "context": {
                    "error": str(exc),
                    "url": PROFILER_API_URL,
                }
            },
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "UPSTREAM_PROFILER_UNAVAILABLE",
                "message": (
                    "Upstream profiler API is temporarily unavailable. "
                    "Please try again later."
                ),
            },
        )
