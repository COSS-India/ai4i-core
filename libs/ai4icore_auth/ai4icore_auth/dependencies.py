"""
Shared FastAPI dependencies for authentication and authorization.

Permission checks use permission_ids (int) from JWT — zero DB round-trip.
ADMIN role bypasses all checks.

Usage::

    from ai4icore_auth.dependencies import create_require_auth, create_require_role

    require_auth = create_require_auth(jwt_verifier)

    @router.post("/inference")
    async def infer(claims: AuthClaims = Depends(require_auth)):
        ...
"""

import logging
from typing import Optional

from fastapi import Depends, Header, Request

from .jwt_verifier import AuthClaims, JWTVerifier, JWTVerificationError, JWTExpiredError
from .permission_checker import PermissionChecker

logger = logging.getLogger(__name__)


def create_require_auth(jwt_verifier: JWTVerifier):
    """Requires a valid JWT. Returns AuthClaims."""

    async def _require_auth(
        request: Request,
        authorization: Optional[str] = Header(None),
    ) -> AuthClaims:
        from ai4icore_exceptions import AuthenticationRequiredError, TokenExpiredError, TokenInvalidError

        if not authorization:
            raise AuthenticationRequiredError()

        token = authorization[7:] if authorization.startswith("Bearer ") else authorization
        if not token:
            raise AuthenticationRequiredError("Empty token.")

        try:
            claims = await jwt_verifier.verify(token)
        except JWTExpiredError:
            raise TokenExpiredError()
        except JWTVerificationError as exc:
            raise TokenInvalidError(exc.message)

        request.state.user_id = claims.user_id
        request.state.tenant_id = claims.tenant_id
        request.state.permission_ids = claims.permission_ids
        request.state.roles = claims.roles
        request.state.token_type = claims.token_type
        request.state.token_id = claims.token_id
        request.state.username = claims.username
        request.state.email = claims.email
        request.state.is_authenticated = True
        request.state.jwt_claims = claims

        return claims

    return _require_auth


def create_require_role(jwt_verifier: JWTVerifier, *role_names: str):
    """Requires valid JWT + at least one of the specified roles."""
    require_auth = create_require_auth(jwt_verifier)

    async def _require_role(
        claims: AuthClaims = Depends(require_auth),
    ) -> AuthClaims:
        from ai4icore_exceptions import InsufficientPermissionsError

        if PermissionChecker.has_any_role(list(role_names), claims.roles):
            return claims

        raise InsufficientPermissionsError("role", " or ".join(role_names))

    return _require_role
