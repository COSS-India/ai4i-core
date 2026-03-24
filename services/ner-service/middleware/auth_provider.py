"""Thin auth wrapper built on existing ai4icore_auth primitives."""

from typing import Optional

from fastapi import Header, Request

from ai4icore_auth import JWTVerifier, PermissionChecker, create_require_auth
from ai4icore_env import app_env
from ai4icore_exceptions import InsufficientPermissionsError

# Service-specific configuration
SERVICE_NAME = "ner"
ACTION_MAP = {"/inference": "inference"}

def _determine_service_and_action(request: Request) -> tuple[str, str]:
    path = request.url.path.lower()
    method = request.method.upper()
    for path_part, action in ACTION_MAP.items():
        if path_part in path:
            return SERVICE_NAME, action
    if method == "GET":
        return SERVICE_NAME, "read"
    return SERVICE_NAME, "read"


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
