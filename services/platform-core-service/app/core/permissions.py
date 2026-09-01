"""Shared role IDs and permission-parsing helper used across all route modules.

A single source of truth means a role-ID change only needs to be made here.
"""
import re
from typing import Optional

from fastapi import HTTPException, Request, status

from app.core.exceptions import InsufficientPermissionsError

ROLE_ADMIN = 1
ROLE_MODERATOR = 2
ROLE_TENANT_ADMIN = 5


def permission_ids(request: Request) -> set[int]:
    """Parse X-Permission-IDS header into a set of integer role IDs."""
    raw = request.headers.get("X-Permission-IDS", "")
    return {int(m) for m in re.findall(r"\d+", raw)}


def is_admin(request: Request) -> bool:
    """Admin-only check (excludes tenant admin/moderator) — used by the PPU usage
    and application-usage dashboards, where only a platform Admin may see data
    across every institution."""
    return bool(permission_ids(request) & {ROLE_ADMIN})


def require_usage_access(request: Request) -> None:
    """Admin or Tenant Admin may call a usage/metering-dashboard endpoint at all;
    which tenant(s) they may see within it is a separate, narrower check —
    see authorize_own_tenant_or_admin."""
    if not permission_ids(request) & {ROLE_ADMIN, ROLE_TENANT_ADMIN}:
        raise InsufficientPermissionsError()


def caller_tenant_id(request: Request) -> Optional[str]:
    """The institution a Tenant Admin caller is scoped to, from the gateway-set
    X-Tenant-Id header. None for a caller with no tenant context (e.g. an Admin)."""
    return request.headers.get("X-Tenant-Id") or None


def authorize_own_tenant_or_admin(request: Request, tenant_id: str) -> None:
    """Shared usage/metering-dashboard tenant boundary: an Admin may view any
    institution's data; a Tenant Admin may only view their own (matched against
    X-Tenant-Id) — used by both /pay-per-use/usage-tenant and every
    /pay-per-use/usage-application* endpoint so the rule can't drift between them.
    """
    require_usage_access(request)
    if is_admin(request):
        return
    caller_tid = caller_tenant_id(request)
    if not caller_tid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin requires a tenant context (X-Tenant-Id).",
        )
    if caller_tid != tenant_id:
        raise InsufficientPermissionsError()
