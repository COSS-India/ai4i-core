"""
RBAC Helper for AI4ICore Telemetry Library

Provides RBAC utilities for extracting organization filters from requests.
Uses shared ai4icore_auth for RS256 JWT verification.
"""
import logging
from typing import Optional, Any
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)


async def _verify_token(request: Request):
    """Verify JWT using shared ai4icore_auth verifier. Returns AuthClaims or raises 401."""
    from ai4icore_auth.providers import build_jwt_verifier
    from ai4icore_auth.jwt_verifier import JWTVerificationError

    authorization = request.headers.get("Authorization") or request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    token = authorization.split(" ", 1)[1]

    verifier = build_jwt_verifier()
    if verifier.loaded_key_count == 0:
        await verifier.initialize()

    try:
        return await verifier.verify(token)
    except JWTVerificationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )


async def get_organization_filter(
    request: Request,
    rbac_enforcer: Any,
    permission: str,
    tenant_id_fallback: Optional[Any] = None
) -> Optional[str]:
    """
    Extract tenant_id filter from request based on RBAC.

    This function:
    1. Verifies JWT token via shared ai4icore_auth (RS256)
    2. Extracts user_id, tenant_id, and roles from claims
    3. Checks Casbin permissions
    4. Returns tenant_id filter (None for admin, tenant_id for users)

    Args:
        request: FastAPI request object
        rbac_enforcer: Casbin enforcer instance
        permission: Permission to check (e.g., "logs.read", "traces.read")
        tenant_id_fallback: Optional async callback to look up tenant_id from DB

    Returns:
        None if user is admin (no filter), tenant_id if normal user

    Raises:
        HTTPException: 401 if no token, 403 if no permission or no tenant_id
    """
    claims = await _verify_token(request)

    user_id = claims.user_id
    tenant_id = claims.tenant_id
    roles = claims.roles

    # Check permission using Casbin
    if "." not in permission:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid permission format: {permission}"
        )

    resource, action = permission.split(".", 1)
    tenant = "default"

    # Check if user has permission
    has_permission = False

    user_sub = f"user:{user_id}"
    if rbac_enforcer.enforce(user_sub, tenant, resource, action):
        has_permission = True
    else:
        for role in roles:
            role_sub = f"role:{role}"
            if rbac_enforcer.enforce(role_sub, tenant, resource, action):
                has_permission = True
                break

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission}"
        )

    # ADMIN sees all (no filter), others see only their tenant
    is_admin = "ADMIN" in roles

    if is_admin:
        logger.debug("Admin user %s - returning None (no filter, sees all)", user_id)
        return None

    # Non-admin must have tenant_id
    if not tenant_id:
        if tenant_id_fallback and callable(tenant_id_fallback):
            try:
                tenant_id = await tenant_id_fallback(user_id)
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Error querying tenant_id for user %s: %s", user_id, e)
                tenant_id = None

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Access denied. You must be associated with a tenant to access logs.",
                    "code": "TENANT_REQUIRED",
                    "hint": "Please register to a tenant. If you recently registered, log out and back in to refresh your token."
                }
            )

    logger.debug("User %s with tenant_id %s - filtering by tenant", user_id, tenant_id)
    return tenant_id


def extract_user_info(request: Request) -> dict:
    """
    Extract user information from request.state (populated by auth middleware/dependency).

    Returns:
        Dict with user_id, tenant_id, roles, email, username
    """
    return {
        "user_id": getattr(request.state, "user_id", None),
        "tenant_id": getattr(request.state, "tenant_id", None),
        "roles": getattr(request.state, "roles", []),
        "email": getattr(request.state, "email", ""),
        "username": getattr(request.state, "username", ""),
    }
