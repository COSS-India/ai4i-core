import logging
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pay_per_use.tier import Tier, TierQuota
from app.repositories.pay_per_use.usage_repository import update_tier_cache
from app.schemas.pay_per_use.tier import TierCreate, TierOut, TierQuotaOut, TierUpdate
from app.services.pay_per_use import inference_type_cache
from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


async def _resolve_task_type_ids(
    session: AsyncSession, task_types: Optional[str]
) -> Optional[List[int]]:
    """Parse ``?task_types=a,b`` into catalogue ids.

    Validates against the live catalogue rather than ``TaskTypeEnum``: the enum is
    a hardcoded list, so filtering by an admin-added type used to 422 even though
    creating a tier with it worked.
    """
    if not task_types:
        return None
    requested = [raw.strip() for raw in task_types.split(",") if raw.strip()]
    if not requested:
        return None

    resolved = await inference_type_cache.get_ids_by_names(session, requested)
    unknown = sorted(name for name, type_id in resolved.items() if type_id is None)
    if unknown:
        known = sorted(entry["name"] for entry in await inference_type_cache.get_all(session))
        raise ValidationError(
            f"Invalid task type '{unknown[0]}'. Valid types: {', '.join(known)}"
        )
    return [type_id for type_id in resolved.values() if type_id is not None] or None


def _build_out(tier: Tier, quotas: List[TierQuota], names: dict) -> TierOut:
    """Serialise a tier. ``names`` is the catalogue's ``{id: name}`` map.

    The API contract is unchanged — ``modelTaskType`` is still the name string —
    but it now comes from the catalogue rather than the denormalised column, so a
    renamed type is reflected immediately.

    The fallback to ``inference_name`` covers a cache miss mid-request. It is
    unreachable in practice once every row carries an id, and it goes away with
    the column.
    """
    quota_out = []
    for q in quotas:
        name = names.get(q.inference_type_id)
        if name is None:
            logger.warning(
                "Tier quota %s has no catalogue entry for inference_type_id=%s; "
                "falling back to the stored inference_name %r",
                q.id, q.inference_type_id, q.inference_name,
            )
            name = q.inference_name
        quota_out.append(
            TierQuotaOut(
                modelTaskType=name,
                limit=q.monthly_quota,
                pendingLimit=q.pending_monthly_quota,
            )
        )

    return TierOut(
        id=str(tier.id),
        name=tier.name,
        description=tier.description,
        quotas=quota_out,
        createdAt=tier.created_at,
        updatedAt=tier.updated_at,
    )


async def list_tiers(
    session: AsyncSession, task_types: Optional[str] = None
) -> dict:
    type_ids = await _resolve_task_type_ids(session, task_types)
    names = await inference_type_cache.get_name_by_id(session)
    stmt = (
        select(Tier)
        .where(Tier.is_active.is_(True))
        .options(selectinload(Tier.tier_quotas))
    )
    result = await session.execute(stmt)
    tiers = result.scalars().all()

    out = []
    for tier in tiers:
        # Comparing ids also fixes a latent bug: the old membership test was
        # case-sensitive, so ?task_types=ASR matched nothing against a quota
        # stored as 'asr'.
        quotas = [
            q for q in tier.tier_quotas
            if not type_ids or q.inference_type_id in type_ids
        ]
        if type_ids and not quotas:
            continue
        out.append(_build_out(tier, quotas, names))

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

    names = await inference_type_cache.get_name_by_id(session)
    return _build_out(tier, tier.tier_quotas, names)


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
        # The catalogue is authoritative for which task types exist — TierQuotaIn
        # only normalises the string. A miss here is the 400 that TaskTypeEnum
        # used to raise at validation time.
        inference_type = await inference_type_cache.get_by_name(session, q.modelTaskType)
        if inference_type is None:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown model task type '{q.modelTaskType}'",
            )
        quota = TierQuota(
            tier_id=tier.id,
            inference_name=q.modelTaskType,
            inference_type_id=inference_type["id"],
            monthly_quota=q.limit,
            created_by=created_by,
            updated_by=created_by,
        )
        session.add(quota)
        quotas.append(quota)

    await session.commit()
    await session.refresh(tier)
    update_tier_cache(tier.id, tier.name)
    names = await inference_type_cache.get_name_by_id(session)
    return _build_out(tier, quotas, names)


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
        # Two distinct 400s now: not in the catalogue at all, versus in the
        # catalogue but not granted on this tier. The second message is
        # user-visible and unchanged.
        type_id = await inference_type_cache.get_id_by_name(session, q.modelTaskType)
        if type_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown model task type '{q.modelTaskType}'",
            )
        q_result = await session.execute(
            select(TierQuota).where(
                TierQuota.tier_id == tier.id,
                TierQuota.inference_type_id == type_id,
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
        # Unknown name stays a silent no-op, matching the existing `if row:`
        # behaviour — a cancel should not start 400ing.
        type_id = await inference_type_cache.get_id_by_name(session, inference_name)
        if type_id is None:
            continue
        q_result = await session.execute(
            select(TierQuota).where(
                TierQuota.tier_id == tier.id,
                TierQuota.inference_type_id == type_id,
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
    names = await inference_type_cache.get_name_by_id(session)
    return _build_out(tier, quotas, names)


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
