"""
FastAPI dependencies for alert-management-service auth.
Uses shared ai4icore_auth library for JWT verification — same as all other services.
"""

from fastapi import Request, Depends

from ai4icore_auth.providers import create_auth_providers
from ai4icore_auth.jwt_verifier import AuthClaims
from ai4icore_exceptions import InsufficientPermissionsError

AuthProvider, OptionalAuthProvider = create_auth_providers()


async def require_alerts_create(
    request: Request,
    claims: AuthClaims = Depends(AuthProvider),
) -> None:
    """Require auth + ADMIN or MODERATOR role for alert creation."""
    if "ADMIN" in claims.roles or "MODERATOR" in claims.roles:
        _set_request_state(request, claims)
        return
    raise InsufficientPermissionsError("alerts", "create")


async def require_alerts_read(
    request: Request,
    claims: AuthClaims = Depends(AuthProvider),
) -> None:
    """Require auth for alert reading. All authenticated users can read."""
    _set_request_state(request, claims)


async def require_alerts_update(
    request: Request,
    claims: AuthClaims = Depends(AuthProvider),
) -> None:
    """Require auth + ADMIN or MODERATOR role for alert updates."""
    if "ADMIN" in claims.roles or "MODERATOR" in claims.roles:
        _set_request_state(request, claims)
        return
    raise InsufficientPermissionsError("alerts", "update")


async def require_alerts_delete(
    request: Request,
    claims: AuthClaims = Depends(AuthProvider),
) -> None:
    """Require auth + ADMIN role for alert deletion."""
    if "ADMIN" in claims.roles:
        _set_request_state(request, claims)
        return
    raise InsufficientPermissionsError("alerts", "delete")


def _set_request_state(request: Request, claims: AuthClaims) -> None:
    """Set request.state for downstream use by routers."""
    request.state.username = claims.username or f"user-{claims.user_id}"
    request.state.user_id = claims.user_id
    request.state.roles = claims.roles
    request.state.is_admin = "ADMIN" in claims.roles
