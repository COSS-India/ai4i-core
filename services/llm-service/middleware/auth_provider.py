"""Thin auth wrapper built on existing ai4icore_auth primitives."""

from typing import Tuple
from typing import Optional

from fastapi import Header, Request

from ai4icore_auth import JWTVerifier, PermissionChecker, create_require_auth
from ai4icore_env import app_env
from ai4icore_exceptions import InsufficientPermissionsError


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    """LLM-specific service/action resolution.

    Extracts service name from URL path (e.g. ``/api/v1/llm/...`` -> ``llm``).
    Falls back to ``"llm"`` when no known service slug is found.
    """
    path = request.url.path.lower()
    method = request.method.upper()

    service = None
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm"]:
        if f"/api/v1/{svc}/" in path or path.endswith(f"/api/v1/{svc}"):
            service = svc
            break
    if not service:
        service = "llm"

    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/services" in path or "/models" in path or "/languages" in path:
        action = "read"
    else:
        action = "read"

    return service, action


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
