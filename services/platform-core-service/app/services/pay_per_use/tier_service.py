import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import TierStatus
from app.core.exceptions import ValidationError
from app.models.pay_per_use.tier import Tier, TierQuota
from app.repositories.pay_per_use.usage_repository import update_tier_cache
from app.schemas.pay_per_use.tier import TierCreate, TierOut, TierQuotaOut, TierUpdate
from app.services.pay_per_use import inference_type_cache
from app.models.pay_per_use.quota_usage import QuotaUsage

logger = logging.getLogger(__name__)

# Bounded retry for the post-reactivation notification to auth-service.
# Transient unreachability (connect error, timeout, 5xx) is retried up to this
# many times so that quota-exhausted flags don't stay set indefinitely from a
# brief outage. 4xx errors are not retried (they won't be fixed by retrying).
_REACTIVATE_NOTIFY_MAX_ATTEMPTS = 3
_REACTIVATE_NOTIFY_BACKOFF = (1.0, 2.0)  # seconds between successive attempts

# Five valid edges; DELETED has no outgoing edge (terminal).
_ALLOWED_TIER_STATUS_TRANSITIONS: dict[TierStatus, frozenset[TierStatus]] = {
    TierStatus.INACTIVE: frozenset({TierStatus.ACTIVE}),
    TierStatus.ACTIVE: frozenset({TierStatus.DEACTIVATED}),
    TierStatus.DEACTIVATED: frozenset({TierStatus.ACTIVE, TierStatus.DELETED}),
    TierStatus.DELETED: frozenset(),
}


def assert_valid_tier_status_transition(current: TierStatus, target: TierStatus) -> None:
    """Raise ValidationError when ``target`` is not reachable from ``current``."""
    if current == target:
        raise ValidationError(
            message=f"Tier status is already {current.value}.",
            code="TIER_STATUS_UNCHANGED",
        )
    allowed = _ALLOWED_TIER_STATUS_TRANSITIONS.get(current, frozenset())
    if target in allowed:
        return
    allowed_labels = ", ".join(sorted(s.value for s in allowed)) or "none"
    raise ValidationError(
        message=(
            f"Cannot change tier status from {current.value} to {target.value}. "
            f"Allowed targets: {allowed_labels}."
        ),
        code="INVALID_TIER_STATUS_TRANSITION",
    )


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
        status=tier.status,
        quotas=quota_out,
        createdAt=tier.created_at,
        updatedAt=tier.updated_at,
    )


async def list_tiers(
    session: AsyncSession,
    task_types: Optional[str] = None,
    status: Optional[TierStatus] = None,
) -> dict:
    type_ids = await _resolve_task_type_ids(session, task_types)
    names = await inference_type_cache.get_name_by_id(session)
    stmt = select(Tier).where(Tier.status != TierStatus.DELETED).options(selectinload(Tier.tier_quotas))
    if status is not None:
        stmt = stmt.where(Tier.status == status)
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
        .where(Tier.id == uid, Tier.status != TierStatus.DELETED)
        .options(selectinload(Tier.tier_quotas))
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{tier_id}' not found")

    names = await inference_type_cache.get_name_by_id(session)
    return _build_out(tier, tier.tier_quotas, names)


async def create_tier(body: TierCreate, session: AsyncSession, created_by: Optional[str] = None) -> TierOut:
    existing = await session.execute(select(Tier).where(Tier.name == body.name, Tier.status != TierStatus.DELETED))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tier with name '{body.name}' already exists",
        )

    tier = Tier(name=body.name, description=body.description, status=TierStatus.INACTIVE, created_by=created_by, updated_by=created_by)
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

    try:
        await session.commit()
    except DBAPIError as exc:
        await session.rollback()
        if "NumericValueOutOfRange" in str(exc.orig) or "numeric field overflow" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Quota limit must be between 0 and 100,000,000,000 (100 billion)",
            )
        raise
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

    result = await session.execute(select(Tier).where(Tier.id == uid, Tier.status != TierStatus.DELETED))
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

    try:
        await session.commit()
    except DBAPIError as exc:
        await session.rollback()
        if "NumericValueOutOfRange" in str(exc.orig) or "numeric field overflow" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Quota limit must be between 0 and 100,000,000,000 (100 billion)",
            )
        raise
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



async def _get_tier_or_404(tier_id: str, session: AsyncSession) -> Tier:
    try:
        uid = UUID(tier_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tier_id format")
    result = await session.execute(select(Tier).where(Tier.id == uid, Tier.status != TierStatus.DELETED))
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tier '{tier_id}' not found")
    return tier


async def update_tier_status(
    tier_id: str,
    target_status: TierStatus,
    session: AsyncSession,
    auth_service_url: str = "",
    http_client: Optional[httpx.AsyncClient] = None,
    auth_db: Optional[AsyncSession] = None,
    updated_by: Optional[str] = None,
) -> TierOut:
    """Single entry point for all tier status transitions.

    Allowed edges (enforced by assert_valid_tier_status_transition):
      INACTIVE    → ACTIVE       (Publish)
      ACTIVE      → DEACTIVATED  (Deactivate)
      DEACTIVATED → ACTIVE       (Reactivate — triggers quota reset + Redis flag clear)
      DEACTIVATED → DELETED      (Delete — only if no tenants are assigned)
    """
    tier = await _get_tier_or_404(tier_id, session)
    previous_status = tier.status
    assert_valid_tier_status_transition(previous_status, target_status)

    if target_status in {TierStatus.DEACTIVATED, TierStatus.DELETED}:
        action = "deactivating" if target_status == TierStatus.DEACTIVATED else "deleting"
        if auth_db is None:
            raise ValidationError(
                message=f"Tier {action} cannot be verified: auth-service DB is not configured.",
                code="AUTH_DB_NOT_CONFIGURED",
            )
        assigned = await auth_db.execute(
            text("SELECT 1 FROM tenants WHERE tier_id = :tier_id LIMIT 1"),
            {"tier_id": tier.id},
        )
        if assigned.first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tier is still assigned to one or more tenants. Reassign them to another tier or remove the tier assignment before {action}.",
            )
        mapped = await session.execute(
            text("SELECT 1 FROM mm_services WHERE :tier_id = ANY(tier_ids) LIMIT 1"),
            {"tier_id": str(tier.id)},
        )
        if mapped.first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tier is still mapped to one or more services. Remove the tier mapping from all services before {action}.",
            )

    # Side effects that must run before commit.
    if target_status == TierStatus.ACTIVE and previous_status == TierStatus.DEACTIVATED:
        # Reactivate: reset monthly quota usage for the current billing month.
        # local import avoids circular
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        await session.execute(
            update(QuotaUsage)
            .where(QuotaUsage.tier_id == tier.id, QuotaUsage.billing_month == current_month)
            .values(monthly_quota_used=0)
        )

    tier.status = target_status
    tier.updated_by = updated_by
    await session.commit()
    await session.refresh(tier)
    update_tier_cache(tier.id, tier.name)

    # Post-commit notifications (best-effort).
    if target_status == TierStatus.ACTIVE and previous_status == TierStatus.DEACTIVATED:
        await _notify_tier_reactivated(tier, auth_service_url, http_client, auth_db)
    elif target_status == TierStatus.DEACTIVATED:
        await _notify_tier_deactivated(tier, auth_service_url, http_client)

    q_result = await session.execute(select(TierQuota).where(TierQuota.tier_id == tier.id))
    names = await inference_type_cache.get_name_by_id(session)
    return _build_out(tier, list(q_result.scalars().all()), names)


async def _notify_tier_reactivated(
    tier: Tier,
    auth_service_url: str,
    http_client: Optional[httpx.AsyncClient],
    auth_db: Optional[AsyncSession],
) -> None:
    if not (auth_service_url and http_client):
        return

    try:
        tenant_ids = await _fetch_tenant_ids_for_tier(tier.id, auth_db)
    except Exception as exc:
        logger.warning(
            "tier-reactivated notification for tier %s skipped: "
            "auth-db query for tenant IDs failed (%s); "
            "quota-exhausted flags may remain set until the next reactivation",
            tier.id, exc,
        )
        return

    payload = {"tier_id": str(tier.id), "tenant_ids": tenant_ids}
    failure: str = "unknown"

    for attempt in range(1, _REACTIVATE_NOTIFY_MAX_ATTEMPTS + 1):
        try:
            resp = await http_client.post(
                f"{auth_service_url}/internal/ppu/tier/reactivated",
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
            return
        except httpx.HTTPStatusError as exc:
            failure = f"HTTP {exc.response.status_code}"
            if exc.response.status_code < 500:
                # 4xx will not be fixed by retrying; log and bail.
                logger.warning(
                    "tier-reactivated notification for tier %s rejected "
                    "(HTTP %s, not retrying): quota-exhausted flags may remain "
                    "set for %d tenant(s)",
                    tier.id, exc.response.status_code, len(tenant_ids),
                )
                return
        except httpx.TimeoutException:
            failure = "request timed out"
        except httpx.ConnectError as exc:
            failure = f"connection refused/unreachable: {exc}"
        except Exception as exc:
            failure = str(exc)

        if attempt < _REACTIVATE_NOTIFY_MAX_ATTEMPTS:
            delay = _REACTIVATE_NOTIFY_BACKOFF[attempt - 1]
            logger.warning(
                "tier-reactivated notification for tier %s failed "
                "(attempt %d/%d, %s); retrying in %.0fs",
                tier.id, attempt, _REACTIVATE_NOTIFY_MAX_ATTEMPTS, failure, delay,
            )
            await asyncio.sleep(delay)

    logger.error(
        "tier-reactivated notification for tier %s failed after %d attempts (%s): "
        "quota-exhausted flags may remain set for %d tenant(s) until next reactivation",
        tier.id, _REACTIVATE_NOTIFY_MAX_ATTEMPTS, failure, len(tenant_ids),
    )


async def _notify_tier_deactivated(
    tier: Tier,
    auth_service_url: str,
    http_client: Optional[httpx.AsyncClient],
) -> None:
    """Push an ACTIVE → DEACTIVATED status change to auth-service immediately after commit.

    Without this push, auth-service coasts on its cached ACTIVE status for up to
    tier_status_cache_refresh_interval_seconds, serving entitled traffic during that
    window. The periodic reload remains as a backstop.
    """
    if not (auth_service_url and http_client):
        return

    payload = {"tier_id": str(tier.id)}
    failure: str = "unknown"

    for attempt in range(1, _REACTIVATE_NOTIFY_MAX_ATTEMPTS + 1):
        try:
            resp = await http_client.post(
                f"{auth_service_url}/internal/ppu/tier/deactivated",
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
            return
        except httpx.HTTPStatusError as exc:
            failure = f"HTTP {exc.response.status_code}"
            if exc.response.status_code < 500:
                logger.warning(
                    "tier-deactivated notification for tier %s rejected "
                    "(HTTP %s, not retrying): auth-service status cache may be stale",
                    tier.id, exc.response.status_code,
                )
                return
        except httpx.TimeoutException:
            failure = "request timed out"
        except httpx.ConnectError as exc:
            failure = f"connection refused/unreachable: {exc}"
        except Exception as exc:
            failure = str(exc)

        if attempt < _REACTIVATE_NOTIFY_MAX_ATTEMPTS:
            delay = _REACTIVATE_NOTIFY_BACKOFF[attempt - 1]
            logger.warning(
                "tier-deactivated notification for tier %s failed "
                "(attempt %d/%d, %s); retrying in %.0fs",
                tier.id, attempt, _REACTIVATE_NOTIFY_MAX_ATTEMPTS, failure, delay,
            )
            await asyncio.sleep(delay)

    logger.error(
        "tier-deactivated notification for tier %s failed after %d attempts (%s): "
        "auth-service will enforce deactivation on next cache reload",
        tier.id, _REACTIVATE_NOTIFY_MAX_ATTEMPTS, failure,
    )
