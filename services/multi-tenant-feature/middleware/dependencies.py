"""
Admin/Tenant-admin role dependencies for multi-tenant-feature.
Reads roles from request.state populated by AuthProvider (shared ai4icore_auth).

Tenant scoping: ADMIN can access any tenant. TENANT ADMIN is scoped
to their own tenant_id from JWT claims.
"""

from fastapi import HTTPException, status, Request, Depends
from middleware.auth_provider import AuthProvider
from logger import logger


async def require_admin(request: Request, _ = Depends(AuthProvider)):
    """Require ADMIN role. Platform-wide access."""
    roles = _get_roles(request)

    if not any(str(r).upper() == "ADMIN" for r in roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required to perform the action",
        )
    request.state.is_platform_admin = True


async def require_tenant_admin(request: Request, _ = Depends(AuthProvider)):
    """Require ADMIN or TENANT ADMIN role.

    Sets request.state for downstream tenant scoping:
    - is_platform_admin: True if ADMIN (can access any tenant)
    - caller_tenant_id: tenant_id from JWT (for TENANT ADMIN scoping)
    """
    roles = _get_roles(request)

    is_admin = any(str(r).upper() == "ADMIN" for r in roles)
    is_tenant_admin = any(str(r).upper() == "TENANT ADMIN" for r in roles)

    if not (is_admin or is_tenant_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to perform the action",
        )

    request.state.is_platform_admin = is_admin

    # Extract caller's tenant_id for scoping
    claims = getattr(request.state, "jwt_claims", None)
    caller_tenant_id = getattr(claims, "tenant_id", None) if claims else None
    request.state.caller_tenant_id = caller_tenant_id


def enforce_tenant_scope(request: Request, target_tenant_id: str) -> None:
    """Verify TENANT ADMIN is accessing their own tenant only.

    ADMIN bypasses this check (platform-wide access).
    Call this in any endpoint that takes a tenant_id parameter.

    Raises:
        HTTPException 403 if TENANT ADMIN tries to access another tenant.
    """
    if getattr(request.state, "is_platform_admin", False):
        return  # ADMIN can access any tenant

    caller_tenant_id = getattr(request.state, "caller_tenant_id", None)
    if not caller_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not associated with any tenant.",
        )

    if caller_tenant_id != target_tenant_id:
        logger.warning(
            "Tenant scope violation: caller_tenant=%s tried to access target_tenant=%s",
            caller_tenant_id, target_tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own tenant's data.",
        )


def _get_roles(request: Request) -> list:
    """Extract roles from request.state."""
    claims = getattr(request.state, "jwt_claims", None)
    if claims:
        return claims.roles
    return getattr(request.state, "roles", None) or []
