"""Tenant tier assignment service."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.ppu_tenant_tier_assignment import PPUTenantTierAssignment
from app.models.pay_per_use.ppu_tier import PPUTier
from app.schemas.pay_per_use.tenant_assignment import (
    ReviseBudgetRequest,
    ReviseBudgetResponse,
    TierAssignRequest,
    TierAssignResponse,
    TierReassignRequest,
)
from app.utils.tenant_validator import require_active_tenant

logger = logging.getLogger(__name__)


async def _notify_auth_best_effort(
    http_client: httpx.AsyncClient,
    url: str,
    *,
    json: Optional[dict] = None,
) -> None:
    """POST to auth-service; log (don't raise) on failure so a billing operation
    is never blocked by a notification error."""
    try:
        resp = await http_client.post(url, json=json, timeout=5.0)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Failed to notify auth-service at %s: %s", url, exc)


async def _resolve_active_tier(db: AsyncSession, tier_id: str) -> PPUTier:
    """Parse ``tier_id`` as a UUID and look up the matching active tier, or raise 400/404."""
    try:
        tier_uuid = UUID(tier_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tier_id format — expected a UUID",
        )
    result = await db.execute(
        select(PPUTier).where(PPUTier.id == tier_uuid, PPUTier.is_active == True)
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tier '{tier_id}' not found or is inactive",
        )
    return tier


async def _lock_active_assignment(
    db: AsyncSession,
    tenant_id: str,
) -> Optional[PPUTenantTierAssignment]:
    """Lock the tenant's currently-active assignment row, or None if it has none.

    Always retries once (a fresh statement, with a freshly re-read "now") if
    the first lookup comes up empty. This guards against races with any
    concurrent call that retires this exact row rather than updating it in
    place (e.g. two overlapping reassign_tier calls, or reassign_tier racing
    revise_budget): under READ COMMITTED, if the first query blocks on a row
    being retired, EvalPlanQual re-checks the WHERE only against that same
    row's new (now-retired) values once unblocked — it does not look at the
    newly inserted replacement row — so the first lookup can spuriously miss
    an assignment that, moments later, clearly exists. The retry must
    re-evaluate "now" fresh (not reuse the first attempt's timestamp): the
    replacement row's effective_from is set by the other transaction's own
    now(), which can be later than our first snapshot, so a stale "now"
    would still fail to match it.
    """
    def _query(now: datetime):
        return (
            select(PPUTenantTierAssignment)
            .where(
                PPUTenantTierAssignment.tenant_id == tenant_id,
                PPUTenantTierAssignment.effective_from <= now,
                PPUTenantTierAssignment.effective_to > now,
            )
            .with_for_update()
        )

    result = await db.execute(_query(datetime.now(timezone.utc)))
    assignment = result.scalar_one_or_none()
    if assignment is None:
        result = await db.execute(_query(datetime.now(timezone.utc)))
        assignment = result.scalar_one_or_none()
    return assignment


async def _require_active_assignment(
    db: AsyncSession,
    tenant_id: str,
) -> PPUTenantTierAssignment:
    """_lock_active_assignment, raising 404 if the tenant has no active assignment."""
    assignment = await _lock_active_assignment(db, tenant_id)
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active tier assignment found for tenant '{tenant_id}'",
        )
    return assignment


def _to_assign_response(
    tenant_id: str, tier: PPUTier, assignment: PPUTenantTierAssignment
) -> TierAssignResponse:
    return TierAssignResponse(
        tenant_id=tenant_id,
        tier_id=str(tier.id),
        tier_name=tier.name,
        budget_limit=assignment.budget_limit,
        available_balance=assignment.available_balance,
        effective_from=assignment.effective_from,
        effective_to=assignment.effective_to,
        updated_at=assignment.updated_at,
    )


async def revise_budget(
    body: ReviseBudgetRequest,
    db: AsyncSession,
    auth_db: AsyncSession,
    auth_service_url: str,
    http_client: httpx.AsyncClient,
    user_id: Optional[str] = None,
) -> ReviseBudgetResponse:
    """Adjust a tenant's Budget by a top-up or top-down amount, effective immediately.

    Validates that the tenant exists and is ACTIVE in the auth DB, matching
    assign_tier/reassign_tier.

    Unlike an absolute set, the new budget is derived from the current
    budget_limit +/- body.amount, matching the Adjust Budget UI (single
    amount field + top-up/top-down toggle) so the caller never has to know
    or compute the current budget_limit itself.

    The reject-on-underflow guards only apply to action='top-down': a
    top-down larger than the current budget_limit (negative result) is
    rejected with 422, and a top-down that would drop below cumulative spend
    to date (old budget_limit - old available_balance) is rejected outright
    with 409 (nothing written) — the Admin must pick a smaller amount, or
    top up instead. A result exactly equal to cumulative spend is accepted
    and leaves available_balance at 0, which blocks the tenant's next
    request immediately. action='top-up' always succeeds once the tenant is
    found and active — it only ever adds headroom, so it must never be
    rejected for being "below spend," even for an already over-spent tenant
    (available_balance already negative from real usage). Tier, Quota
    Limit, and Rate Limit are untouched.
    """
    await require_active_tenant(body.tenant_id, auth_db)

    assignment = await _require_active_assignment(db, body.tenant_id)

    delta = body.amount if body.action == "top-up" else -body.amount
    new_budget = assignment.budget_limit + delta

    if body.action == "top-down":
        if new_budget < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Top-down amount ({body.amount}) exceeds the current budget "
                    f"({assignment.budget_limit})"
                ),
            )
        consumed = assignment.budget_limit - assignment.available_balance
        if new_budget < consumed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "budget_exceeded",
                    "message": (
                        f"Revised budget ({new_budget}) is below cumulative spend "
                        f"to date ({consumed}) — revision rejected"
                    ),
                },
            )

    new_balance = assignment.available_balance + delta
    result = await db.execute(
        text(
            "UPDATE ppu_tenant_tier_assignments"
            "   SET budget_limit      = :new_budget,"
            "       available_balance = :new_balance,"
            "       updated_by        = :updated_by,"
            "       updated_at        = now()"
            " WHERE id = :id"
            " RETURNING updated_at"
        ),
        {
            "new_budget": new_budget,
            "new_balance": new_balance,
            "updated_by": user_id,
            "id": assignment.id,
        },
    )
    updated_at = result.scalar_one()
    await db.commit()

    exhausted = new_balance <= 0
    if auth_service_url:
        # Best-effort: billing stays correct; Redis flag will self-correct on next consumer event.
        await _notify_auth_best_effort(
            http_client,
            f"{auth_service_url}/internal/ppu/tenant/{body.tenant_id}/budget-exhausted",
            json={"exhausted": exhausted},
        )

    return ReviseBudgetResponse(
        tenant_id=body.tenant_id,
        budget_limit=new_budget,
        available_balance=new_balance,
        updated_at=updated_at,
    )


async def assign_tier(
    body: TierAssignRequest,
    db: AsyncSession,
    auth_db: AsyncSession,
    user_id: Optional[str] = None,
    auth_service_url: Optional[str] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> TierAssignResponse:
    # 1. Confirm tenant exists and is ACTIVE via auth DB.
    await require_active_tenant(body.tenant_id, auth_db)

    # 2. Validate the tier_id and confirm it exists and is active in platform-core DB.
    tier = await _resolve_active_tier(db, body.tier_id)

    if body.effective_to <= body.effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_to must be after effective_from",
        )
    if body.effective_to - body.effective_from < timedelta(days=1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Effective From and Effective To cannot be the same date.",
        )

    now = datetime.now(timezone.utc)
    today_utc = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if body.effective_from < today_utc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_from cannot be in the past",
        )

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

    if auth_service_url and http_client:
        # Best-effort: a tenant billed with no active tier (see payperuse_consumer's
        # fail-closed check) may have quota-{tasktype} flags stuck from before this
        # assignment existed. Clear them now instead of leaving the tenant 429'd
        # until the monthly cron runs.
        await _notify_auth_best_effort(
            http_client,
            f"{auth_service_url}/internal/ppu/tenant/{body.tenant_id}/quota-reset",
        )

    return _to_assign_response(body.tenant_id, tier, assignment)


async def reassign_tier(
    body: TierReassignRequest,
    db: AsyncSession,
    auth_db: AsyncSession,
    user_id: Optional[str] = None,
    auth_service_url: Optional[str] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> TierAssignResponse:
    """Move a tenant to a different tier, effective immediately.

    Unlike assign_tier, this does not take a budget: available_balance and
    budget_limit carry over unchanged from the assignment being replaced.
    The old assignment is closed as of now(); a new one opens for the new
    tier, running through the same original effective_to. Usage/cost tracking
    (ppu_quota_usage) keys on tier_id, so it starts fresh under the new tier.
    """
    # 1. Confirm tenant exists and is ACTIVE via auth DB.
    await require_active_tenant(body.tenant_id, auth_db)

    new_tier = await _resolve_active_tier(db, body.tier_id)

    now = datetime.now(timezone.utc)

    # Lock the tenant's current active assignment so a concurrent billing event
    # can't read a half-updated row while this transaction is in flight.
    current = await _require_active_assignment(db, body.tenant_id)

    if current.tier_id == new_tier.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant '{body.tenant_id}' is already on tier '{new_tier.name}'",
        )

    original_effective_to = current.effective_to

    # Reject if the replacement window overlaps a future-dated assignment
    # (the current row being closed is excluded since it's being replaced).
    overlapping = await db.execute(
        select(PPUTenantTierAssignment).where(
            PPUTenantTierAssignment.tenant_id == body.tenant_id,
            PPUTenantTierAssignment.id != current.id,
            PPUTenantTierAssignment.effective_from < original_effective_to,
            PPUTenantTierAssignment.effective_to > now,
        )
    )
    if overlapping.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant '{body.tenant_id}' has a future tier assignment overlapping the reassignment period",
        )

    current.effective_to = now
    current.updated_by = user_id

    new_assignment = PPUTenantTierAssignment(
        tenant_id=body.tenant_id,
        tier_id=new_tier.id,
        budget_limit=current.budget_limit,
        available_balance=current.available_balance,
        effective_from=now,
        effective_to=original_effective_to,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(new_assignment)
    await db.commit()
    await db.refresh(new_assignment)

    if auth_service_url and http_client:
        # Best-effort: unlike the budget flag, this does not self-heal on the next
        # consumer event — the tenant stays 429'd until the monthly cron runs if lost.
        await _notify_auth_best_effort(
            http_client,
            f"{auth_service_url}/internal/ppu/tenant/{body.tenant_id}/quota-reset",
        )

    return _to_assign_response(body.tenant_id, new_tier, new_assignment)


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

        # Distinguish "tier exists, zero current assignments" (200 + []) from
        # "tier_id doesn't exist at all" (404) — matches GET /tier/{tier_id}.
        tier_exists = await db.execute(
            select(PPUTier.id).where(
                PPUTier.id == tier_uuid, PPUTier.is_active.is_(True)
            )
        )
        if tier_exists.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tier '{tier_id}' not found",
            )

        query = query.where(PPUTenantTierAssignment.tier_id == tier_uuid)

    result = await db.execute(query)
    rows = result.all()

    return [
        _to_assign_response(assignment.tenant_id, tier, assignment)
        for assignment, tier in rows
    ]
