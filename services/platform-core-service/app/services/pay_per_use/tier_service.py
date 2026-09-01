import logging
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pay_per_use.tier import Tier, TierQuota
from app.repositories.pay_per_use.usage_repository import update_tier_cache
from app.schemas.pay_per_use.tier import TierCreate, TierOut, TierQuotaOut, TierUpdate
from app.schemas.enums.model_management import resolve_task_type
from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _resolve_task_types(task_types: Optional[str]) -> Optional[List[str]]:
    if not task_types:
        return None
    resolved = []
    for raw in task_types.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            resolved.append(resolve_task_type(raw))
        except ValueError as exc:
            raise ValidationError(str(exc))
    return resolved or None


def _build_out(tier: Tier, quotas: List[TierQuota]) -> TierOut:
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
    session: AsyncSession, task_types: Optional[str] = None
) -> dict:
    model_task_types = _resolve_task_types(task_types)
    stmt = (
        select(Tier)
        .where(Tier.is_active.is_(True))
        .options(selectinload(Tier.tier_quotas))
    )
    result = await session.execute(stmt)
    tiers = result.scalars().all()

    out = []
    for tier in tiers:
        quotas = [q for q in tier.tier_quotas if not model_task_types or q.inference_name in model_task_types]
        if model_task_types and not quotas:
            continue
        out.append(_build_out(tier, quotas))

    return {"data": out, "total": len(out)}


async def get_tier_by_id(tier_id: str, session: AsyncSession) -> TierOut:
    try:
        uid = UUID(tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")

    result = await session.execute(
        select(Tier)
        .where(Tier.id == uid, Tier.is_active.is_(True))
        .options(selectinload(Tier.tier_quotas))
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{tier_id}' not found")

    return _build_out(tier, tier.tier_quotas)


async def create_tier(body: TierCreate, session: AsyncSession, created_by: Optional[str] = None) -> TierOut:
    existing = await session.execute(select(Tier).where(Tier.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tier with name '{body.name}' already exists",
        )

    tier = Tier(name=body.name, description=body.description, created_by=created_by, updated_by=created_by)
    session.add(tier)
    await session.flush()

    quotas = []
    for q in body.quotas:
        quota = TierQuota(
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
    update_tier_cache(tier.id, tier.name)
    return _build_out(tier, quotas)


async def _fetch_tenant_ids_for_tier(tier_id, auth_db: Optional[AsyncSession]) -> list:
    """Tenants currently on ``tier_id`` — for the best-effort
    quota-limit-updated webhook to auth-service, so it knows who to notify.

    ppu_tenant_tier_assignments was dropped (AI4IDS-2923); tenants.tier_id
    (auth-service, via auth_db) is the sole source of truth now — no
    effective_from/effective_to window to check, since that column has no
    expiry (same fact already established fixing get_tenant_budgets and
    auth-service's assign_tenant_tier). auth_db unavailable degrades to no
    tenants found, matching this function's existing best-effort framing —
    the caller already treats the whole notification as skippable.
    """
    if auth_db is None:
        return []
    result = await auth_db.execute(
        text("SELECT id FROM tenants WHERE tier_id = :tier_id"),
        {"tier_id": tier_id},
    )
    return [row.id for row in result.all()]


async def _resolve_tier_for_update(body: TierUpdate, session: AsyncSession) -> Tier:
    try:
        uid = UUID(body.tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")

    result = await session.execute(select(Tier).where(Tier.id == uid, Tier.is_active.is_(True)))
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{body.tier_id}' not found")
    return tier


async def _upsert_quotas(
    session: AsyncSession, tier: Tier, quotas: List, updated_by: Optional[str]
) -> None:
    for q in quotas:
        q_result = await session.execute(
            select(TierQuota).where(
                TierQuota.tier_id == tier.id,
                func.lower(TierQuota.inference_name) == q.modelTaskType.lower(),
            )
        )
        existing = q_result.scalar_one_or_none()
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Model task type '{q.modelTaskType}' does not exist in this tier. Adding new model task types is not allowed via update.",
            )
        existing.pending_monthly_quota = q.limit
        existing.updated_by = updated_by


async def _cancel_pending_quotas(
    session: AsyncSession, tier: Tier, inference_names: List[str], updated_by: Optional[str]
) -> None:
    for inference_name in inference_names:
        q_result = await session.execute(
            select(TierQuota).where(
                TierQuota.tier_id == tier.id,
                func.lower(TierQuota.inference_name) == inference_name.lower(),
            )
        )
        row = q_result.scalar_one_or_none()
        if row:
            row.pending_monthly_quota = None
            row.updated_by = updated_by


async def _notify_tier_updated(
    tier: Tier,
    auth_service_url: str,
    http_client: Optional[httpx.AsyncClient],
    auth_db: Optional[AsyncSession],
) -> None:
    if not (auth_service_url and http_client):
        return

    try:
        tenant_ids = await _fetch_tenant_ids_for_tier(tier.id, auth_db)
        resp = await http_client.post(
            f"{auth_service_url}/internal/ppu/tier/quota-limit-updated",
            json={"tier_name": tier.name, "tenant_ids": tenant_ids},
            timeout=5.0,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("quota-limit-updated notification failed for tier %s: %s", tier.id, exc)


async def update_tier(
    body: TierUpdate,
    session: AsyncSession,
    updated_by: Optional[str] = None,
    auth_service_url: str = "",
    http_client: Optional[httpx.AsyncClient] = None,
    auth_db: Optional[AsyncSession] = None,
) -> TierOut:
    tier = await _resolve_tier_for_update(body, session)

    if body.name is not None:
        tier.name = body.name
    if body.description is not None:
        tier.description = body.description
    tier.updated_by = updated_by

    if body.quotas is not None:
        await _upsert_quotas(session, tier, body.quotas, updated_by)

    if body.cancel_pending_quota:
        await _cancel_pending_quotas(session, tier, body.cancel_pending_quota, updated_by)

    await session.commit()
    await session.refresh(tier)
    update_tier_cache(tier.id, tier.name)

    if body.quotas is not None or body.cancel_pending_quota:
        await _notify_tier_updated(tier, auth_service_url, http_client, auth_db)

    q_result = await session.execute(select(TierQuota).where(TierQuota.tier_id == tier.id))
    quotas = list(q_result.scalars().all())
    return _build_out(tier, quotas)


async def apply_pending_quotas(session: AsyncSession) -> int:
    """Promote pending_monthly_quota → monthly_quota for all tiers.
    Called by the monthly billing-cycle cron on the 1st of each month.
    Returns the number of quota rows updated.
    """
    result = await session.execute(
        select(TierQuota).where(TierQuota.pending_monthly_quota.isnot(None))
    )
    rows = result.scalars().all()
    for row in rows:
        row.monthly_quota = row.pending_monthly_quota
        row.pending_monthly_quota = None
    await session.commit()
    return len(rows)


async def delete_tier(tier_id: str, session: AsyncSession, auth_db: Optional[AsyncSession]) -> None:
    try:
        uid = UUID(tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")

    result = await session.execute(
        select(Tier).where(Tier.id == uid, Tier.is_active.is_(True))
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{tier_id}' not found")

    # ppu_tenant_tier_assignments was dropped (AI4IDS-2923); tenants.tier_id
    # (auth-service, via auth_db) is the sole source of truth now — see
    # _fetch_tenant_ids_for_tier. Unlike that best-effort notification, this
    # is a genuine safety guard (deleting an in-use tier breaks billing
    # enforcement for its tenants), so an unavailable auth_db must fail
    # closed here, not silently skip the check — same convention as
    # auth-service's assign_tenant_tier's PLATFORM_CORE_DB_NOT_CONFIGURED.
    if auth_db is None:
        raise ValidationError(
            message="Tier deletion cannot be verified: auth-service DB is not configured.",
            code="AUTH_DB_NOT_CONFIGURED",
        )
    assigned = await auth_db.execute(
        text("SELECT 1 FROM tenants WHERE tier_id = :tier_id LIMIT 1"),
        {"tier_id": uid},
    )
    if assigned.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tier is assigned to one or more tenants and cannot be deleted",
        )

    tier.is_active = False
    await session.commit()
    update_tier_cache(tier.id, tier.name)
