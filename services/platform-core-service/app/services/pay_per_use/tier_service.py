from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.ppu_tier import PPUTier, PPUTierQuota
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.schemas.pay_per_use.tier import TierCreate, TierOut, TierQuotaOut, TierUpdate


def _build_out(tier: PPUTier, quotas: List[PPUTierQuota]) -> TierOut:
    return TierOut(
        id=str(tier.id),
        name=tier.name,
        description=tier.description,
        quotas=[
            TierQuotaOut(
                modelTaskType=q.inference_name,
                limit=q.monthly_quota,
            )
            for q in quotas
        ],
        createdAt=tier.created_at,
        updatedAt=tier.updated_at,
    )


async def list_tiers(
    session: AsyncSession, model_task_type: Optional[str] = None
) -> dict:
    result = await session.execute(select(PPUTier).where(PPUTier.is_active == True))
    tiers = result.scalars().all()

    out = []
    for tier in tiers:
        q_result = await session.execute(
            select(PPUTierQuota).where(PPUTierQuota.tier_id == tier.id)
        )
        quotas = q_result.scalars().all()

        if model_task_type:
            quotas = [q for q in quotas if q.inference_name == model_task_type]
            if not quotas:
                continue

        out.append(_build_out(tier, quotas))

    return {"data": out, "total": len(out)}


async def get_tier_by_id(tier_id: str, session: AsyncSession) -> TierOut:
    try:
        uid = UUID(tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")

    result = await session.execute(select(PPUTier).where(PPUTier.id == uid))
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{tier_id}' not found")

    q_result = await session.execute(select(PPUTierQuota).where(PPUTierQuota.tier_id == tier.id))
    quotas = q_result.scalars().all()
    return _build_out(tier, quotas)


async def create_tier(body: TierCreate, session: AsyncSession, created_by: Optional[str] = None) -> TierOut:
    existing = await session.execute(select(PPUTier).where(PPUTier.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tier with name '{body.name}' already exists",
        )

    tier = PPUTier(name=body.name, description=body.description, created_by=created_by, updated_by=created_by)
    session.add(tier)
    await session.flush()

    quotas = []
    for q in body.quotas:
        quota = PPUTierQuota(
            tier_id=tier.id,
            inference_name=q.modelTaskType,
            monthly_quota=q.limit,
            created_by=created_by,
            updated_by=created_by,
        )
        session.add(quota)
        quotas.append(quota)

    await session.commit()
    await session.refresh(tier)
    return _build_out(tier, quotas)


async def update_tier(body: TierUpdate, session: AsyncSession, updated_by: Optional[str] = None) -> TierOut:
    result = await session.execute(select(PPUTier).where(PPUTier.name == body.name))
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{body.name}' not found")

    if body.description is not None:
        tier.description = body.description
    tier.updated_by = updated_by

    if body.quotas is not None:
        await session.execute(delete(PPUTierQuota).where(PPUTierQuota.tier_id == tier.id))
        quotas = []
        for q in body.quotas:
            quota = PPUTierQuota(
                tier_id=tier.id,
                inference_name=q.modelTaskType,
                monthly_quota=q.limit,
                created_by=updated_by,
                updated_by=updated_by,
            )
            session.add(quota)
            quotas.append(quota)
    else:
        q_result = await session.execute(select(PPUTierQuota).where(PPUTierQuota.tier_id == tier.id))
        quotas = q_result.scalars().all()

    await session.commit()
    await session.refresh(tier)
    return _build_out(tier, quotas)


async def delete_tier(tier_id: str, session: AsyncSession) -> None:
    try:
        uid = UUID(tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")

    result = await session.execute(select(PPUTier).where(PPUTier.id == uid))
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{tier_id}' not found")

    assigned = await session.execute(
        select(PPUTenantTierAssignment).where(PPUTenantTierAssignment.tier_id == uid).limit(1)
    )
    if assigned.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tier is assigned to one or more tenants and cannot be deleted",
        )

    await session.delete(tier)
    await session.commit()
