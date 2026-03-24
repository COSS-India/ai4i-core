"""
Endpoint-level permission guard using api_permissions.json mapping.

Shared across ALL microservices. Checks if METHOD:PATH requires a
permission code (P_XX) and verifies the authenticated user has it
in their JWT claims — zero DB round-trip.

Usage::

    from ai4icore_auth.endpoint_guard import create_endpoint_guard

    guard = create_endpoint_guard(jwt_verifier, redis_client)

    @router.post("/inference")
    async def infer(claims = Depends(guard)):
        ...
"""

import logging
from typing import Optional, Callable

from fastapi import Depends, Request

from .jwt_verifier import AuthClaims, JWTVerifier
from .permission_checker import PermissionChecker

logger = logging.getLogger(__name__)


def create_endpoint_guard(
    jwt_verifier: JWTVerifier,
    permission_checker: Optional[PermissionChecker] = None,
) -> Callable:
    """
    Create a FastAPI dependency that enforces endpoint-level permissions
    from the api_permissions.json mapping cached in Redis.

    Flow:
    1. Verify JWT → get AuthClaims
    2. Look up METHOD:PATH in Redis → get required permission code (P_XX)
    3. If null → public endpoint, allow
    4. If user's permission_codes include it → allow
    5. Otherwise → 403
    """
    from .dependencies import create_require_auth
    require_auth = create_require_auth(jwt_verifier)

    async def _guard(
        request: Request,
        claims: AuthClaims = Depends(require_auth),
    ) -> AuthClaims:
        if permission_checker is None:
            logger.warning("Endpoint guard: no permission_checker configured — allowing all authenticated requests.")
            return claims

        required_code = await permission_checker.get_required_permission(
            request.method, request.url.path,
        )

        if PermissionChecker.check_endpoint_access(
            required=required_code,
            user_permission_ids=claims.permission_ids,
            user_permission_codes=claims.permission_codes,
            user_roles=claims.roles,
        ):
            return claims

        from ai4icore_exceptions import InsufficientPermissionsError
        logger.warning(
            "Endpoint denied: user=%s %s:%s requires=%s has=%s",
            claims.user_id, request.method, request.url.path,
            required_code, claims.permission_codes,
        )
        raise InsufficientPermissionsError(request.url.path, request.method)

    return _guard
