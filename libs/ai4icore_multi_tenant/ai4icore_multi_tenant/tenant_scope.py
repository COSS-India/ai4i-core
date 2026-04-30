"""
Tenant scoping for route handlers: ADMIN vs TENANT ADMIN.

Used by services that populate ``request.state`` via AuthMiddleware and/or
tenant-admin dependencies (``is_platform_admin``, ``caller_tenant_id``).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


def enforce_tenant_scope(
    request: Request,
    target_tenant_id: Optional[str],
    *,
    is_platform_admin: Optional[bool] = None,
    caller_tenant_id: Optional[str] = None,
) -> None:
    """Verify TENANT ADMIN only acts within their tenant.

    Platform ADMIN bypasses when ``is_platform_admin`` is true. Resolution:

    - ``is_platform_admin``: explicit argument, else ``request.state.is_platform_admin``,
      else true if ``request.state.roles`` contains ``ADMIN`` (case-insensitive).
    - ``caller_tenant_id``: explicit argument, else ``request.state.caller_tenant_id``,
      else ``request.state.tenant_id`` (from AuthMiddleware).

    Args:
        request: Starlette/FastAPI request.
        target_tenant_id: Tenant id of the resource or target user. ``None`` or
            empty string fails the check for non-admin callers.

    Raises:
        HTTPException: 403 when the caller may not access the target tenant.
    """
    if is_platform_admin is None:
        is_platform_admin = bool(getattr(request.state, "is_platform_admin", False))
        if not is_platform_admin:
            roles = getattr(request.state, "roles", None) or []
            is_platform_admin = any(str(r).upper() == "ADMIN" for r in roles)

    if is_platform_admin:
        return

    resolved_caller = caller_tenant_id
    if resolved_caller is None:
        resolved_caller = getattr(request.state, "caller_tenant_id", None)
    if resolved_caller is None:
        resolved_caller = getattr(request.state, "tenant_id", None)

    if not resolved_caller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not associated with any tenant.",
        )

    if not target_tenant_id:
        logger.warning(
            "Tenant scope violation: tenant admin tenant=%s target has no tenant",
            resolved_caller,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage users in your own tenant.",
        )

    if str(resolved_caller) != str(target_tenant_id):
        logger.warning(
            "Tenant scope violation: caller_tenant=%s tried to access target_tenant=%s",
            resolved_caller,
            target_tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own tenant's data.",
        )
