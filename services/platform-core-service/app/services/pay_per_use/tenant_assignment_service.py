"""Tenant tier assignment service."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier
from app.schemas.pay_per_use.tenant_assignment import TierAssignRequest, TierAssignResponse, TopUpRequest, TopUpResponse
from app.utils.tenant_validator import require_active_tenant


async def top_up_budget(
    body: TopUpRequest,
    db: AsyncSession,
    auth_service_url: str,
    http_client: httpx.AsyncClient,
) -> TopUpResponse:
    result = await db.execute(
        text(
            "UPDATE ppu_tenant_tier_assignments"
            "   SET available_balance = available_balance + :amount,"
            "       budget_limit      = budget_limit + :amount,"
            "       updated_at        = now()"
            " WHERE tenant_id = :tenant_id"
            "   AND effective_from <= now()"
            "   AND effective_to   >  now()"
            " RETURNING available_balance"
        ),
        {"amount": body.amount, "tenant_id": body.tenant_id},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active tier assignment found for tenant '{body.tenant_id}'",
        )
    await db.commit()

    new_balance: Decimal = row.available_balance
    if new_balance > 0 and auth_service_url:
        try:
            resp = await http_client.post(
                f"{auth_service_url}/internal/ppu/tenant/{body.tenant_id}/budget-exhausted",
                json={"exhausted": False},
                timeout=5.0,
            )
            resp.raise_for_status()
        except Exception:
            pass  # billing stays correct; Redis flag will self-correct on next consumer event

    return TopUpResponse(
        tenant_id=body.tenant_id,
        added=body.amount,
        available_balance=new_balance,
    )


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

    # 4. Reject if the new date range overlaps with any existing assignment.
    existing = await db.execute(
        select(PPUTenantTierAssignment).where(
            PPUTenantTierAssignment.tenant_id == body.tenant_id,
            PPUTenantTierAssignment.effective_from < body.effective_to,
            PPUTenantTierAssignment.effective_to > body.effective_from,
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant '{body.tenant_id}' already has a tier assignment overlapping the requested period",
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


async def list_tenant_tiers(
    db: AsyncSession,
    tier_id: Optional[str] = None,
) -> list[TierAssignResponse]:
    now = datetime.now(timezone.utc)

    query = (
        select(PPUTenantTierAssignment, PPUTier)
        .join(PPUTier, PPUTenantTierAssignment.tier_id == PPUTier.id)
        .where(PPUTenantTierAssignment.effective_to > now)
    )

    if tier_id is not None:
        try:
            tier_uuid = UUID(tier_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tier_id format — expected a UUID",
            )
        query = query.where(PPUTenantTierAssignment.tier_id == tier_uuid)

    result = await db.execute(query)
    rows = result.all()

    return [
        TierAssignResponse(
            tenant_id=assignment.tenant_id,
            tier_id=str(tier.id),
            tier_name=tier.name,
            budget_limit=assignment.budget_limit,
            available_balance=assignment.available_balance,
            effective_from=assignment.effective_from,
            effective_to=assignment.effective_to,
            updated_at=assignment.updated_at,
        )
        for assignment, tier in rows
    ]
