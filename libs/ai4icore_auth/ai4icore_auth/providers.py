"""
Shared auth provider factory for all microservices.

Eliminates duplicated AuthProvider / OptionalAuthProvider boilerplate.
Each service only needs to call create_auth_providers() with optional overrides.

Usage::

    from ai4icore_auth.providers import create_auth_providers

    # Standard service (most services)
    AuthProvider, OptionalAuthProvider = create_auth_providers()

    # Service with anonymous access (e.g. try-it)
    def _allow_anonymous(request):
        return request.url.path.endswith("/api/v1/try-it")

    AuthProvider, OptionalAuthProvider = create_auth_providers(
        allow_anonymous=_allow_anonymous,
    )
"""

import asyncio
import logging
from typing import Callable, Optional

from fastapi import Header, Request

from .jwt_verifier import JWTVerifier, AuthClaims
from .permission_checker import PermissionChecker
from .dependencies import create_require_auth

logger = logging.getLogger(__name__)

_init_lock = asyncio.Lock()


def build_jwt_verifier() -> JWTVerifier:
    """Build a JWTVerifier from standard env settings (ai4icore_env)."""
    from ai4icore_env import app_env

    jwks_url = app_env.jwks_url
    if not jwks_url:
        auth_service_url = (app_env.auth_service_url or "").rstrip("/")
        jwks_path = (app_env.jwks_path or "").lstrip("/")
        if auth_service_url and jwks_path:
            jwks_url = f"{auth_service_url}/{jwks_path}"
    issuer = app_env.jwt_issuer or app_env.jwt_issuer_url
    audience = app_env.jwt_audience
    return JWTVerifier(jwks_url=jwks_url, issuer=issuer, audience=audience)


def _is_auth_disabled() -> bool:
    """Check if auth is disabled via env."""
    from ai4icore_env import app_env

    if app_env.auth_enabled is None:
        return False
    return str(app_env.auth_enabled).lower() not in ("true", "1", "yes")


def create_auth_providers(
    allow_anonymous: Optional[Callable[[Request], bool]] = None,
) -> tuple:
    """
    Create AuthProvider and OptionalAuthProvider FastAPI dependencies.

    Args:
        allow_anonymous: Optional callback that receives the Request and returns
                         True if the request should be allowed without auth.
                         Examples: try-it endpoints, public APIs.

    Returns:
        (AuthProvider, OptionalAuthProvider) tuple of FastAPI dependency functions.
    """
    jwt_verifier = build_jwt_verifier()
    require_auth = create_require_auth(jwt_verifier)
    _permission_checker: Optional[PermissionChecker] = None

    async def AuthProvider(
        request: Request,
        authorization: Optional[str] = Header(None),
    ) -> Optional[AuthClaims]:
        nonlocal _permission_checker

        if _is_auth_disabled():
            return None

        if allow_anonymous and allow_anonymous(request):
            return None

        if jwt_verifier.loaded_key_count == 0:
            async with _init_lock:
                if jwt_verifier.loaded_key_count == 0:
                    await jwt_verifier.initialize()

        claims = await require_auth(request=request, authorization=authorization)

        if _permission_checker is None:
            redis_client = getattr(request.app.state, "redis_client", None)
            _permission_checker = PermissionChecker(redis_client=redis_client)

        required = await _permission_checker.get_required_permission(
            request.method, request.url.path,
        )
        if PermissionChecker.check_endpoint_access(
            required=required,
            user_permission_ids=claims.permission_ids,
            user_permission_codes=claims.permission_codes,
            user_roles=claims.roles,
        ):
            return claims

        from ai4icore_exceptions import InsufficientPermissionsError
        raise InsufficientPermissionsError(request.url.path, request.method)

    async def OptionalAuthProvider(
        request: Request,
        authorization: Optional[str] = Header(None),
    ) -> Optional[AuthClaims]:
        if not authorization:
            return None
        try:
            return await AuthProvider(request=request, authorization=authorization)
        except Exception:
            logger.debug("OptionalAuthProvider: auth failed, returning None", exc_info=True)
            return None

    return AuthProvider, OptionalAuthProvider
