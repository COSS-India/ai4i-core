"""
Admin/Tenant-admin role dependencies for multi-tenant-feature.
Reads roles from request.state populated by AuthProvider (shared ai4icore_auth).
"""

from fastapi import HTTPException, status, Request, Depends
from middleware.auth_provider import AuthProvider
from logger import logger


async def require_admin(request: Request, _ = Depends(AuthProvider)):
    """Require ADMIN role."""
    roles = getattr(request.state, "roles", None) or []
    claims = getattr(request.state, "jwt_claims", None)
    if claims:
        roles = claims.roles

    if not any(str(r).upper() == "ADMIN" for r in roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required to perform the action",
        )


async def require_tenant_admin(request: Request, _ = Depends(AuthProvider)):
    """Require ADMIN or TENANT ADMIN role."""
    roles = getattr(request.state, "roles", None) or []
    claims = getattr(request.state, "jwt_claims", None)
    if claims:
        roles = claims.roles

    is_admin = any(str(r).upper() == "ADMIN" for r in roles)
    is_tenant_admin = any(str(r).upper() == "TENANT ADMIN" for r in roles)

    if not (is_admin or is_tenant_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to perform the action",
        )
