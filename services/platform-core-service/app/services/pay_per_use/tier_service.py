import logging
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pay_per_use.ppu_tier import PPUTier, PPUTierQuota
from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.schemas.pay_per_use.tier import TierCreate, TierOut, TierQuotaOut, TierUpdate

logger = logging.getLogger(__name__)


def _build_out(tier: PPUTier, quotas: List[PPUTierQuota]) -> TierOut:
    return TierOut(
        id=str(tier.id),
        name=tier.name,
        description=tier.description,
        quotas=[
            TierQuotaOut(
                modelTaskType=q.inference_name,
                limit=q.monthly_quota,
                pendingLimit=q.pending_monthly_quota,
            )
            for q in quotas
        ],
        createdAt=tier.created_at,
        updatedAt=tier.updated_at,
    )


async def list_tiers(
    session: AsyncSession, model_task_type: Optional[str] = None
) -> dict:
    stmt = (
        select(PPUTier)
        .where(PPUTier.is_active.is_(True))
        .options(selectinload(PPUTier.tier_quotas))
    )
    result = await session.execute(stmt)
    tiers = result.scalars().all()

    out = []
    for tier in tiers:
        quotas = tier.tier_quotas
        if model_task_type and not any(q.inference_name == model_task_type for q in quotas):
            continue
        out.append(_build_out(tier, quotas))

    return {"data": out, "total": len(out)}


async def get_tier_by_id(tier_id: str, session: AsyncSession) -> TierOut:
    try:
        uid = UUID(tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")

    result = await session.execute(
        select(PPUTier)
        .where(PPUTier.id == uid, PPUTier.is_active.is_(True))
        .options(selectinload(PPUTier.tier_quotas))
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{tier_id}' not found")

    return _build_out(tier, tier.tier_quotas)


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


async def _fetch_tenant_ids_for_tier(tier_id, session: AsyncSession) -> list:
    result = await session.execute(
        select(PPUTenantTierAssignment.tenant_id).where(
            PPUTenantTierAssignment.tier_id == tier_id,
            PPUTenantTierAssignment.effective_from <= func.now(),
            PPUTenantTierAssignment.effective_to > func.now(),
        )
    )
    return [row.tenant_id for row in result.all()]


async def update_tier(
    body: TierUpdate,
    session: AsyncSession,
    updated_by: Optional[str] = None,
    auth_service_url: str = "",
    http_client: Optional[httpx.AsyncClient] = None,
) -> TierOut:
    try:
        uid = UUID(body.tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")

    result = await session.execute(select(PPUTier).where(PPUTier.id == uid, PPUTier.is_active.is_(True)))
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{body.tier_id}' not found")

    if body.name is not None:
        tier.name = body.name
    if body.description is not None:
        tier.description = body.description
    tier.updated_by = updated_by

    if body.quotas is not None:
        for q in body.quotas:
            q_result = await session.execute(
                select(PPUTierQuota).where(
                    PPUTierQuota.tier_id == tier.id,
                    PPUTierQuota.inference_name == q.modelTaskType,
                )
            )
            existing = q_result.scalar_one_or_none()
            if existing:
                existing.pending_monthly_quota = q.limit
                existing.updated_by = updated_by
            else:
                # New quota type: no active value to preserve, so apply immediately.
                # Setting monthly_quota=0 with the real value only in pending would
                # make units_used >= 0 always true and block all tenants until cycle reset.
                session.add(PPUTierQuota(
                    tier_id=tier.id,
                    inference_name=q.modelTaskType,
                    monthly_quota=q.limit,
                    created_by=updated_by,
                    updated_by=updated_by,
                ))

    if body.cancel_pending_quota:
        for inference_name in body.cancel_pending_quota:
            q_result = await session.execute(
                select(PPUTierQuota).where(
                    PPUTierQuota.tier_id == tier.id,
                    PPUTierQuota.inference_name == inference_name,
                )
            )
            row = q_result.scalar_one_or_none()
            if row:
                row.pending_monthly_quota = None
                row.updated_by = updated_by

    if body.remove_quota:
        await session.execute(
            delete(PPUTierQuota).where(
                PPUTierQuota.tier_id == tier.id,
                PPUTierQuota.inference_name.in_(body.remove_quota),
            )
        )
        await session.flush()
        remaining_result = await session.execute(
            select(func.count()).select_from(PPUTierQuota).where(PPUTierQuota.tier_id == tier.id)
        )
        if remaining_result.scalar() == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove all quotas: at least one model task type must remain in the tier",
            )

    await session.commit()
    await session.refresh(tier)

    if (body.quotas is not None or body.cancel_pending_quota or body.remove_quota) and auth_service_url and http_client:
        tenant_ids = await _fetch_tenant_ids_for_tier(tier.id, session)
        try:
            resp = await http_client.post(
                f"{auth_service_url}/internal/ppu/tier/quota-limit-updated",
                json={"tier_name": tier.name, "tenant_ids": tenant_ids},
                timeout=5.0,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("quota-limit-updated notification failed for tier %s: %s", tier.id, exc)

    q_result = await session.execute(select(PPUTierQuota).where(PPUTierQuota.tier_id == tier.id))
    quotas = list(q_result.scalars().all())
    return _build_out(tier, quotas)


async def apply_pending_quotas(session: AsyncSession) -> int:
    """Promote pending_monthly_quota → monthly_quota for all tiers.
    Called by the monthly billing-cycle cron on the 1st of each month.
    Returns the number of quota rows updated.
    """
    result = await session.execute(
        select(PPUTierQuota).where(PPUTierQuota.pending_monthly_quota.isnot(None))
    )
    rows = result.scalars().all()
    for row in rows:
        row.monthly_quota = row.pending_monthly_quota
        row.pending_monthly_quota = None
    await session.commit()
    return len(rows)


async def delete_tier(tier_id: str, session: AsyncSession) -> None:
    try:
        uid = UUID(tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")

    result = await session.execute(
        select(PPUTier).where(PPUTier.id == uid, PPUTier.is_active.is_(True))
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{tier_id}' not found")

    assigned = await session.execute(
        select(PPUTenantTierAssignment).where(
            PPUTenantTierAssignment.tier_id == uid,
            PPUTenantTierAssignment.effective_to > func.now(),
        ).limit(1)
    )
    if assigned.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tier is assigned to one or more tenants and cannot be deleted",
        )

    tier.is_active = False
    await session.commit()
