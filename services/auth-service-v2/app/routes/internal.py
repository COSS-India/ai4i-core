"""
Internal endpoints — called by other services, not exposed via APISIX.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.responses import success_response
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["Internal"])


class TenantStatusSyncRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=100)
    tenant_status: str = Field(..., description="ACTIVE, SUSPENDED, or DEACTIVATED")


class UserStatusSyncRequest(BaseModel):
    user_id: int
    user_status: str = Field(..., description="ACTIVE, SUSPENDED, or DEACTIVATED")


@router.post("/tenant-status-sync")
async def sync_tenant_status(
    body: TenantStatusSyncRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update tenant_status for all users in a tenant.
    Called by multi-tenant service when tenant status changes."""
    result = await db.execute(
        update(User)
        .where(User.tenant_id == body.tenant_id)
        .values(tenant_status=body.tenant_status.upper())
    )
    await db.commit()
    return success_response(data={
        "tenant_id": body.tenant_id,
        "tenant_status": body.tenant_status.upper(),
        "users_updated": result.rowcount,
    })


@router.post("/user-status-sync")
async def sync_user_status(
    body: UserStatusSyncRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update user_status for a specific user.
    Called by multi-tenant service when tenant user status changes."""
    result = await db.execute(
        update(User)
        .where(User.id == body.user_id)
        .values(user_status=body.user_status.upper())
    )
    await db.commit()
    return success_response(data={
        "user_id": body.user_id,
        "user_status": body.user_status.upper(),
        "updated": result.rowcount > 0,
    })
