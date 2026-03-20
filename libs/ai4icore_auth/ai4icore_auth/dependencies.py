"""
Shared FastAPI dependencies for authentication and authorization.

Permission checks use this priority:
1. permission_codes (P_XX) from JWT — fastest, no DB
2. permissions (names like asr.inference) from JWT — fallback
3. ADMIN role bypass

Usage::

    from ai4icore_auth.dependencies import create_require_auth, create_require_permission

    require_auth = create_require_auth(jwt_verifier)
    require_asr = create_require_permission(jwt_verifier, resource="asr", action="inference")
    require_by_code = create_require_permission_code(jwt_verifier, "P_10")

    @router.post("/inference")
    async def infer(claims: AuthClaims = Depends(require_asr)):
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
        request.state.is_authenticated = True
        request.state.jwt_claims = claims

        return claims

    return _require_auth


def create_require_permission(
    jwt_verifier: JWTVerifier,
    resource: str,
    action: str,
    permission_code: Optional[str] = None,
):
    """
    Requires valid JWT + the specified permission.

    Check order:
    1. permission_code (P_XX) in claims.permission_codes — fastest, no DB
    2. resource.action in claims.permissions — name-based check
    3. ADMIN role bypass

    Args:
        permission_code: Optional P_XX code. If provided, checked first.
                         If not provided, only name-based check is used.
    """
    require_auth = create_require_auth(jwt_verifier)

    async def _require_permission(
        claims: AuthClaims = Depends(require_auth),
    ) -> AuthClaims:
        from ai4icore_exceptions import InsufficientPermissionsError

        # 1. Check by P_XX code (fastest — directly from JWT, no DB)
        if permission_code and permission_code in claims.permission_codes:
            return claims

        # 2. Check by permission name (resource.action)
        required_name = f"{resource}.{action}"
        if PermissionChecker.has_permission(required_name, claims.permissions):
            return claims

        # 3. ADMIN bypass
        if "ADMIN" in claims.roles:
            return claims

        raise InsufficientPermissionsError(resource, action)

    return _require_permission


def create_require_permission_code(
    jwt_verifier: JWTVerifier,
    permission_code: str,
):
    """
    Requires valid JWT + the specified permission code (P_XX).
    Checks permission_codes from JWT — no DB round-trip needed.
    """
    require_auth = create_require_auth(jwt_verifier)

    async def _require_code(
        claims: AuthClaims = Depends(require_auth),
    ) -> AuthClaims:
        from ai4icore_exceptions import InsufficientPermissionsError

        if permission_code in claims.permission_codes:
            return claims
        if "ADMIN" in claims.roles:
            return claims

        raise InsufficientPermissionsError(permission_code, "access")

    return _require_code


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
