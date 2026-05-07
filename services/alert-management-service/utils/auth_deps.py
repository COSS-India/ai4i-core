"""
FastAPI dependencies for alert-management-service auth.
Auth validation is delegated to API gateway (APISIX/nginx).
Services read pre-validated identity headers: X-User-ID, X-Tenant-ID, X-Roles.
"""

from typing import Optional
from fastapi import Request, Header, HTTPException, Depends
from ai4icore_exceptions import InsufficientPermissionsError


async def require_alerts_create(
    request: Request,
    x_roles: Optional[str] = Header(None, alias="X-Roles"),
    x_user_id: str = Header(..., alias="X-User-ID"),
) -> None:
    """Require auth + ADMIN or MODERATOR role for alert creation."""
    roles = (x_roles or "").split(",") if x_roles else []
    if "ADMIN" not in roles and "MODERATOR" not in roles:
        raise InsufficientPermissionsError("alerts", "create")
    request.state.user_id = x_user_id
    request.state.roles = roles
    request.state.is_admin = "ADMIN" in roles


async def require_alerts_read(
    request: Request,
    x_user_id: str = Header(..., alias="X-User-ID"),
    x_roles: Optional[str] = Header(None, alias="X-Roles"),
) -> None:
    """Require auth for alert reading. All authenticated users can read."""
    roles = (x_roles or "").split(",") if x_roles else []
    request.state.user_id = x_user_id
    request.state.roles = roles
    request.state.is_admin = "ADMIN" in roles


async def require_alerts_update(
    request: Request,
    x_user_id: str = Header(..., alias="X-User-ID"),
    x_roles: Optional[str] = Header(None, alias="X-Roles"),
) -> None:
    """Require auth + ADMIN or MODERATOR role for alert updates."""
    roles = (x_roles or "").split(",") if x_roles else []
    if "ADMIN" not in roles and "MODERATOR" not in roles:
        raise InsufficientPermissionsError("alerts", "update")
    request.state.user_id = x_user_id
    request.state.roles = roles
    request.state.is_admin = "ADMIN" in roles


async def require_alerts_delete(
    request: Request,
    x_user_id: str = Header(..., alias="X-User-ID"),
    x_roles: Optional[str] = Header(None, alias="X-Roles"),
) -> None:
    """Require auth + ADMIN role for alert deletion."""
    roles = (x_roles or "").split(",") if x_roles else []
    if "ADMIN" not in roles:
        raise InsufficientPermissionsError("alerts", "delete")
    request.state.user_id = x_user_id
    request.state.roles = roles
    request.state.is_admin = True
