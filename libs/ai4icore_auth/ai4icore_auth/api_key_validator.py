"""API key validation strategies — auth-service remote and local DB."""

import logging
from typing import Optional, Dict, Any

import httpx

from ai4icore_constants.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvalidAPIKeyError,
    ExpiredAPIKeyError,
)

logger = logging.getLogger(__name__)


async def validate_api_key_via_auth_service(
    api_key: str,
    service: str,
    action: str,
    auth_service_url: str,
    auth_http_timeout: float = 5.0,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Validate API key by calling the auth-service.

    POST ``{auth_service_url}/api/v1/auth/validate-api-key``

    Returns the auth-service response dict on success.
    Raises AuthenticationError / AuthorizationError on failure.
    """
    if not api_key:
        raise AuthenticationError("API key is required")

    url = f"{auth_service_url}/api/v1/auth/validate-api-key"
    payload: Dict[str, Any] = {
        "api_key": api_key,
        "service": service,
        "action": action,
    }
    if user_id is not None:
        payload["user_id"] = user_id

    try:
        async with httpx.AsyncClient(timeout=auth_http_timeout) as client:
            response = await client.post(url, json=payload)

        if response.status_code == 200:
            data = response.json()
            if data.get("valid") is True:
                return data
            # valid=false — permission denied
            message = data.get("message", "API key validation failed")
            raise AuthorizationError(message)

        # Non-200 status
        try:
            error_data = response.json()
            detail = error_data.get("detail", error_data.get("message", ""))
        except Exception:
            detail = response.text

        if response.status_code == 401:
            raise InvalidAPIKeyError(detail or "Invalid API key")
        if response.status_code == 403:
            raise AuthorizationError(detail or "Permission denied")

        raise AuthenticationError(
            f"Auth service returned {response.status_code}: {detail}"
        )

    except httpx.TimeoutException:
        logger.error("Auth service timeout: %s", url)
        raise AuthenticationError("Authentication service timeout")
    except httpx.RequestError as exc:
        logger.error("Auth service connection error: %s", exc)
        raise AuthenticationError("Authentication service unavailable")


async def validate_api_key_local(
    api_key: str,
    api_key_repository,
    redis_client=None,
    cache_ttl: int = 300,
) -> Dict[str, Any]:
    """Validate API key against the local database with optional Redis cache.

    Returns dict with api_key_id, user_id, api_key_name, user_email.
    """
    from .headers import hash_api_key

    key_hash = hash_api_key(api_key)

    # Check Redis cache
    if redis_client:
        try:
            import json

            cached = await redis_client.get(f"api_key:{key_hash}")
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # Database lookup
    api_key_db = await api_key_repository.find_by_key_hash(key_hash)
    if not api_key_db:
        raise InvalidAPIKeyError("API key not found")

    if hasattr(api_key_db, "is_key_valid") and not api_key_db.is_key_valid():
        raise ExpiredAPIKeyError("API key is expired or inactive")

    result = {
        "api_key_id": api_key_db.id,
        "user_id": api_key_db.user_id,
        "api_key_name": getattr(api_key_db, "name", None),
        "user_email": None,
    }

    # Update last_used
    if hasattr(api_key_repository, "update_last_used"):
        try:
            await api_key_repository.update_last_used(api_key_db.id)
        except Exception:
            pass

    # Cache result
    if redis_client:
        try:
            import json

            await redis_client.set(
                f"api_key:{key_hash}",
                json.dumps(result),
                ex=cache_ttl,
            )
        except Exception:
            pass

    return result
