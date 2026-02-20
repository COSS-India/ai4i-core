"""
FastAPI dependencies for alert-management-service auth (when used standalone, e.g. behind APISIX).
Require Bearer JWT, validate via auth-service, check permission, set request.state.
"""
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from utils.auth_client import verify_token

# Bearer token scheme (same as gateway: auto_error=False so we can return custom 401 body)
bearer_scheme = HTTPBearer(auto_error=False)

# Permission constants (must match gateway check_permission usage)
ALERTS_CREATE = "alerts.create"
ALERTS_READ = "alerts.read"
ALERTS_UPDATE = "alerts.update"
ALERTS_DELETE = "alerts.delete"

AUTH_FAILED = "AUTH_FAILED"
AUTH_FAILED_MESSAGE = "Authentication failed. Please log in again."


async def require_alert_permission(
    permission: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> None:
    """
    Require Bearer token, validate with auth-service, check that user has the given permission.
    Sets request.state.username, user_id, permissions, roles for use by routers.
    Raises 401 if not authenticated, 403 if permission missing.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": AUTH_FAILED,
                "message": "Bearer access token required for alert management",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = await verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": AUTH_FAILED, "message": AUTH_FAILED_MESSAGE},
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_permissions = payload.get("permissions", [])
    if permission not in user_permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "PERMISSION_DENIED",
                "message": f"Permission '{permission}' required",
            },
        )
    # Set request state so get_username_from_request and is_admin_user work
    request.state.username = payload.get("username") or f"user-{payload.get('sub', 'unknown')}"
    request.state.user_id = payload.get("user_id") or payload.get("sub")
    request.state.permissions = payload.get("permissions", [])
    request.state.roles = payload.get("roles", [])
    request.state.is_admin = (
        "alerts.admin" in user_permissions
        or "ADMIN" in [str(r).upper() for r in payload.get("roles", [])]
    )


async def require_alerts_create(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> None:
    await require_alert_permission(ALERTS_CREATE, request, credentials)


async def require_alerts_read(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> None:
    await require_alert_permission(ALERTS_READ, request, credentials)


async def require_alerts_update(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> None:
    await require_alert_permission(ALERTS_UPDATE, request, credentials)


async def require_alerts_delete(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> None:
    await require_alert_permission(ALERTS_DELETE, request, credentials)
