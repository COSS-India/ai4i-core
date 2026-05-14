"""
RBAC Helper for AI4ICore Telemetry Library

Provides RBAC utilities for extracting organization filters from requests.
Auth validation is delegated to API gateway; this reads pre-validated headers.
"""
import logging
from typing import Optional, Any
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)


async def get_organization_filter(
    request: Request,
    rbac_enforcer: Any,
    permission: str,
    tenant_id_fallback: Optional[Any] = None
) -> Optional[str]:
    """
    Extract tenant_id filter from request based on RBAC.

    This function:
    1. Reads user_id, tenant_id, and roles from gateway-injected headers
    2. Checks Casbin permissions
    3. Returns tenant_id filter (None for admin, tenant_id for users)

    Args:
        request: FastAPI request object
        rbac_enforcer: Casbin enforcer instance
        permission: Permission to check (e.g., "logs.read", "traces.read")
        tenant_id_fallback: Optional async callback to look up tenant_id from DB

    Returns:
        None if user is admin (no filter), tenant_id if normal user

    Raises:
        HTTPException: 401 if no User-ID header, 403 if no permission or no tenant_id
    """
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-ID header (gateway auth required)"
        )

    tenant_id = request.headers.get("X-Tenant-ID")
    roles_header = request.headers.get("X-Roles", "")
    roles = [r.strip() for r in roles_header.split(",")] if roles_header else []

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
