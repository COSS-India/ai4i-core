"""Tenant tier assignment service."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier
from app.schemas.pay_per_use.tenant_assignment import TierAssignRequest, TierAssignResponse
from app.utils.tenant_validator import require_active_tenant


async def assign_tier(
    body: TierAssignRequest,
    db: AsyncSession,
    auth_db: AsyncSession,
    user_id: Optional[str] = None,
) -> TierAssignResponse:
    # 1. Confirm tenant exists and is ACTIVE via auth DB.
    await require_active_tenant(body.tenant_id, auth_db)

    # 2. Validate tier UUID format.
    try:
        tier_uuid = UUID(body.tier_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tier_id format — expected a UUID",
        )

    # 3. Confirm the tier exists and is active in platform-core DB.
    result = await db.execute(
        select(PPUTier).where(PPUTier.id == tier_uuid, PPUTier.is_active == True)
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tier '{body.tier_id}' not found or is inactive",
        )

    if body.effective_to <= body.effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_to must be after effective_from",
        )

    now = datetime.now(timezone.utc)

    # 4. Reject if tenant already has an active tier assignment.
    existing = await db.execute(
        select(PPUTenantTierAssignment).where(
            PPUTenantTierAssignment.tenant_id == body.tenant_id,
            PPUTenantTierAssignment.effective_to > now,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant '{body.tenant_id}' already has an active tier assignment",
        )

    # 5. Create the new assignment.
    assignment = PPUTenantTierAssignment(
        tenant_id=body.tenant_id,
        tier_id=tier.id,
        budget_limit=body.budget,
        available_balance=body.budget,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return TierAssignResponse(
        tenant_id=body.tenant_id,
        tier_id=str(tier.id),
        tier_name=tier.name,
        budget_limit=assignment.budget_limit,
        available_balance=assignment.available_balance,
        effective_from=assignment.effective_from,
        effective_to=assignment.effective_to,
        updated_at=assignment.updated_at,
    )
