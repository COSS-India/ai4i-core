"""
Bare API-key validation endpoint for load-test latency measurement.

/test carries no in-app auth dependency and no permission/quota/tier side
logic — just the same Redis-only API key lookup used by /auth/validate's
API-key branch (validation.py:_validate_api_key), timed in isolation. Used to
separate gateway (APISIX) key-validation overhead from backend processing
time during load tests: point the gateway's key-validation check at this
endpoint and read validation_time_ms back as the actual backend cost to
subtract from the gateway's total.

JWT auth tokens are out of scope here — only the hex API-key path is timed.
"""

import time
from typing import Optional

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import InvalidAPIKeyError
from app.core.redis import get_redis
from app.services.api_key_service import APIKeyService
from app.services.cache_service import CacheService

router = APIRouter(tags=["Test"])


def _extract_token(request: Request, api_key: Optional[str]) -> str:
    """Bearer token from Authorization header, falling back to ?api_key=."""
    raw = request.headers.get("Authorization", "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    if raw:
        return raw
    return (api_key or "").strip()


@router.get("/test")
async def test_api_key_validation(
    request: Request,
    api_key: Optional[str] = None,
    redis=Depends(get_redis),
):
    """
    Validate an API key — via Authorization: Bearer <key> or ?api_key=<key>
    (header takes precedence) — and report how long the validation itself
    took. Always 200 — `valid` carries the real result, not the HTTP status,
    so load-test tooling never has to branch on status code.
    """
    token = _extract_token(request, api_key)
    cache_svc = CacheService(redis)
    api_key_svc = APIKeyService(None, cache_svc)

    start = time.perf_counter()
    try:
        result = await api_key_svc.validate_api_key(token)
        valid = bool(result.get("valid"))
    except InvalidAPIKeyError:
        valid = False
    validation_time_ms = round((time.perf_counter() - start) * 1000, 3)

    return {"valid": valid, "validation_time_ms": validation_time_ms}
