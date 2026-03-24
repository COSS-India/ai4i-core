"""Thin auth wrapper built on existing ai4icore_auth primitives.

Re-exports ``validate_api_key`` and ``hash_api_key`` for
``services/streaming_service.py`` which imports them from here.
"""

import hashlib
import json
import logging
from typing import Optional, Tuple

from fastapi import Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth import JWTVerifier, PermissionChecker, create_require_auth
from ai4icore_exceptions import InsufficientPermissionsError
from ai4icore_env import app_env
from ai4icore_constants.exceptions import (
    AuthenticationError,
    InvalidAPIKeyError,
    ExpiredAPIKeyError,
)

logger = logging.getLogger(__name__)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Service / action resolution (ASR-specific, multi-service path matching)
# ---------------------------------------------------------------------------

def determine_service_and_action(request: Request) -> Tuple[str, str]:
    path = request.url.path.lower()
    method = request.method.upper()

    # Resolve service from URL path when present: /api/v1/<service>/...
    service = None
    path_parts = [segment for segment in path.split("/") if segment]
    if len(path_parts) >= 3 and path_parts[0] == "api" and path_parts[1] == "v1":
        service = path_parts[2]

    # Fallback to configured service identity.
    if not service:
        configured_service = (app_env.service_name or "").lower()
        if configured_service.endswith("-service"):
            configured_service = configured_service[:-8]
        service = configured_service or "unknown"

    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/services" in path or "/models" in path or "/languages" in path:
        action = "read"
    else:
        action = "read"

    return service, action


# ---------------------------------------------------------------------------
# Legacy local-DB API key validation (used by streaming_service.py)
# ---------------------------------------------------------------------------

async def validate_api_key(api_key: str, db: AsyncSession, redis_client):
    """Validate API key locally via DB + Redis cache.

    Returns ``(api_key_db, user_db)`` tuple -- kept for backward-compat
    with ``streaming_service.py``.
    """
    from repositories.api_key_repository import ApiKeyRepository

    try:
        key_hash = hash_api_key(api_key)
        cache_key = f"api_key:{key_hash}"
        cached_data = await redis_client.get(cache_key)

        if cached_data:
            try:
                cache_data = json.loads(cached_data)
                api_key_id = cache_data.get("api_key_id")
                is_active = cache_data.get("is_active", False)
                if is_active:
                    api_key_repo = ApiKeyRepository(db)
                    api_key_db = await api_key_repo.find_by_id(api_key_id)
                    if api_key_db and await api_key_repo.is_key_valid(api_key_db):
                        await api_key_repo.update_last_used(api_key_id)
                        return api_key_db, api_key_db.user
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Invalid cache data for API key: %s", exc)

        api_key_repo = ApiKeyRepository(db)
        api_key_db = await api_key_repo.find_by_key_hash(key_hash)
        if not api_key_db:
            raise InvalidAPIKeyError("API key not found")

        if not await api_key_repo.is_key_valid(api_key_db):
            if not api_key_db.is_active:
                raise InvalidAPIKeyError("API key is inactive")
            raise ExpiredAPIKeyError("API key has expired")

        cache_data = {
            "api_key_id": api_key_db.id,
            "user_id": api_key_db.user_id,
            "is_active": api_key_db.is_active,
        }
        await redis_client.setex(cache_key, app_env.api_key_cache_ttl, json.dumps(cache_data))
        await api_key_repo.update_last_used(api_key_db.id)
        return api_key_db, api_key_db.user

    except (InvalidAPIKeyError, ExpiredAPIKeyError):
        raise
    except Exception as exc:
        logger.error("Error validating API key: %s", exc)
        raise AuthenticationError("Failed to validate API key")


def _build_jwt_verifier() -> JWTVerifier:
    auth_service_url = (app_env.auth_service_url or "").rstrip("/")
    jwks_url = app_env.jwks_url or (
        f"{auth_service_url}/api/v1/auth/.well-known/jwks.json" if auth_service_url else None
    )
    issuer = app_env.jwt_issuer or app_env.jwt_issuer_url
    audience = app_env.jwt_audience
    return JWTVerifier(jwks_url=jwks_url, issuer=issuer, audience=audience)


_jwt_verifier = _build_jwt_verifier()
_require_auth = create_require_auth(_jwt_verifier)


async def AuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    if app_env.auth_enabled is not None and str(app_env.auth_enabled).lower() not in ("true", "1", "yes"):
        return None

    if _jwt_verifier.loaded_key_count == 0:
        await _jwt_verifier.initialize()

    claims = await _require_auth(request=request, authorization=authorization)
    permission_checker = PermissionChecker(redis_client=getattr(request.app.state, "redis_client", None))
    required = await permission_checker.get_required_permission(request.method, request.url.path)
    if PermissionChecker.check_endpoint_access(
        required=required,
        user_permission_ids=claims.permission_ids,
        user_permission_codes=claims.permission_codes,
        user_roles=claims.roles,
    ):
        return claims
    raise InsufficientPermissionsError(request.url.path, request.method)


async def OptionalAuthProvider(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    if not authorization:
        return None
    try:
        return await AuthProvider(request=request, authorization=authorization)
    except Exception:
        return None
