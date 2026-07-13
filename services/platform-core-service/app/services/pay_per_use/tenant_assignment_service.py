"""Tenant tier assignment service."""

import logging
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
from app.schemas.pay_per_use.tenant_assignment import (
    ReviseBudgetRequest,
    ReviseBudgetResponse,
    TierAssignRequest,
    TierAssignResponse,
    TierReassignRequest,
    TopUpRequest,
    TopUpResponse,
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
        # Best-effort: billing stays correct; Redis flag will self-correct on next consumer event.
        await _notify_auth_best_effort(
            http_client,
            f"{auth_service_url}/internal/ppu/tenant/{body.tenant_id}/budget-exhausted",
            json={"exhausted": False},
        )

    return TopUpResponse(
        tenant_id=body.tenant_id,
        added=body.amount,
        available_balance=new_balance,
    )


async def revise_budget(
    body: ReviseBudgetRequest,
    db: AsyncSession,
    auth_service_url: str,
    http_client: httpx.AsyncClient,
    user_id: Optional[str] = None,
) -> ReviseBudgetResponse:
    """Adjust a tenant's Budget by a top-up or top-down amount, effective immediately.

    Unlike an absolute set, the new budget is derived from the current
    budget_limit +/- body.amount, matching the Adjust Budget UI (single
    amount field + top-up/top-down toggle) so the caller never has to know
    or compute the current budget_limit itself.

    Rejected outright (409, nothing written) if the resulting budget would be
    below cumulative spend to date (old budget_limit - old available_balance)
    — the Admin must pick a smaller top-down amount, or top up instead. A
    result exactly equal to cumulative spend is accepted and leaves
    available_balance at 0, which blocks the tenant's next request
    immediately. A top-down larger than the current budget_limit (negative
    result) is rejected with 422. Tier, Quota Limit, and Rate Limit are
    untouched.
    """
    now = datetime.now(timezone.utc)

    def _lock_query():
        return (
            select(PPUTenantTierAssignment)
            .where(
                PPUTenantTierAssignment.tenant_id == body.tenant_id,
                PPUTenantTierAssignment.effective_from <= now,
                PPUTenantTierAssignment.effective_to > now,
            )
            .with_for_update()
        )

    # Lock the active assignment so a concurrent billing event can't shift
    # cumulative spend between the compare and the write.
    result = await db.execute(_lock_query())
    assignment = result.scalar_one_or_none()
    if assignment is None:
        # A concurrent reassign_tier may have just retired this exact row and
        # inserted its replacement. Under READ COMMITTED, if the query above
        # blocked on that row's lock, Postgres's EvalPlanQual re-checks the
        # WHERE only against that same row's new (now-retired) values once
        # unblocked — it does not look at the newly inserted replacement row,
        # so this can spuriously come back empty even though a valid active
        # assignment exists moments later. A fresh query (its own snapshot)
        # reliably finds the replacement if one now exists.
        result = await db.execute(_lock_query())
        assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active tier assignment found for tenant '{body.tenant_id}'",
        )

    delta = body.amount if body.action == "top-up" else -body.amount
    new_budget = assignment.budget_limit + delta
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

    assignment.budget_limit = new_budget
    assignment.available_balance += delta
    assignment.updated_by = user_id
    await db.commit()
    await db.refresh(assignment)

    exhausted = assignment.available_balance <= 0
    if auth_service_url:
        # Best-effort: billing stays correct; Redis flag will self-correct on next consumer event.
        await _notify_auth_best_effort(
            http_client,
            f"{auth_service_url}/internal/ppu/tenant/{body.tenant_id}/budget-exhausted",
            json={"exhausted": exhausted},
        )

    return ReviseBudgetResponse(
        tenant_id=body.tenant_id,
        budget_limit=assignment.budget_limit,
        available_balance=assignment.available_balance,
        updated_at=assignment.updated_at,
    )


async def assign_tier(
    body: TierAssignRequest,
    db: AsyncSession,
    auth_db: AsyncSession,
    user_id: Optional[str] = None,
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
    result = await db.execute(
        select(PPUTenantTierAssignment)
        .where(
            PPUTenantTierAssignment.tenant_id == body.tenant_id,
            PPUTenantTierAssignment.effective_from <= now,
            PPUTenantTierAssignment.effective_to > now,
        )
        .with_for_update()
    )
    current = result.scalar_one_or_none()
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active tier assignment found for tenant '{body.tenant_id}'",
        )

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
        query = query.where(PPUTenantTierAssignment.tier_id == tier_uuid)

    result = await db.execute(query)
    rows = result.all()

    return [
        _to_assign_response(assignment.tenant_id, tier, assignment)
        for assignment, tier in rows
    ]
