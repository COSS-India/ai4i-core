"""Reusable tenant validation against the auth DB (ai4iplatform_auth).

Platform-core holds a read-only secondary connection to the auth DB.
This module provides a single entry point for any feature that needs to
confirm a tenant exists and is ACTIVE before performing an operation.

Usage:
    tenant = await require_active_tenant(tenant_id, auth_db)
    # tenant["id"], tenant["name"], tenant["status"] are available
"""

from typing import Any, Dict

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def require_active_tenant(tenant_id: str, auth_db: AsyncSession) -> Dict[str, Any]:
    """Look up a tenant in the auth DB and assert it is ACTIVE.

    Args:
        tenant_id: String tenant identifier (numeric string matching auth DB
                   ``tenants.id`` integer PK).
        auth_db:   AsyncSession bound to the secondary auth_db engine.

    Returns:
        Dict with ``id``, ``name``, and ``status`` from the auth DB.

    Raises:
        422 if tenant_id is not a valid integer.
        404 if no tenant with that ID exists (including a well-formed
            numeric ID outside Postgres' int4 range, since ``tenants.id``
            can never hold such a value).
        422 if the tenant exists but is not ACTIVE
             (PENDING / SUSPENDED / DEACTIVATED).
    """
    try:
        tenant_int_id = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid tenant ID '{tenant_id}': must be a numeric identifier",
        )

    # tenants.id is a Postgres int4 column; a value outside its range would
    # otherwise reach asyncpg and raise an unhandled NumericValueOutOfRange
    # error (500) instead of the documented 404.
    if not (-2147483648 <= tenant_int_id <= 2147483647):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )

    row = await auth_db.execute(
        text("SELECT id, name, status FROM tenants WHERE id = :tid"),
        {"tid": tenant_int_id},
    )
    tenant = row.first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )

    if tenant.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tenant is '{tenant.status}' — must be ACTIVE to perform this operation",
        )

    return {"id": tenant.id, "name": tenant.name, "status": tenant.status}
