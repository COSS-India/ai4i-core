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


async def _carry_forward_quota_usage(
    db: AsyncSession,
    tenant_id: str,
    old_tier_id: UUID,
    new_tier_id: UUID,
    billing_month: str,
) -> None:
    """Seed the new tier's ppu_quota_usage row(s) with the old tier's accumulated
    cost_accum for this billing month, so a reader keyed on the tenant's current
    tier never sees a missing row between reassignment and the tenant's next
    usage call under the new tier. Quota (units_used) is scoped per-tier by
    design — it starts at 0 under the new tier — while cost/budget is scoped
    per-tenant, so cost_accum carries forward. Only carries forward
    inference_name rows the new tier also has a quota configured for —
    update_quota_usage skips recording usage entirely when no ppu_tier_quotas
    row exists, so seeding one here would create an orphaned row nothing else
    would ever update.
    """
    old_rows = await db.execute(
        text(
            "SELECT inference_name, cost_accum"
            " FROM ppu_quota_usage"
            " WHERE tenant_id = :tenant_id AND billing_month = :billing_month"
            "   AND tier_id = :old_tier_id"
        ),
        {"tenant_id": tenant_id, "billing_month": billing_month, "old_tier_id": old_tier_id},
    )
    for row in old_rows.all():
        snap_result = await db.execute(
            text(
                "SELECT monthly_quota FROM ppu_tier_quotas"
                " WHERE tier_id = :tier_id AND inference_name = :inference_name"
            ),
            {"tier_id": new_tier_id, "inference_name": row.inference_name},
        )
        monthly_quota = snap_result.scalar()
        if monthly_quota is None:
            continue

        await db.execute(
            text(
                "INSERT INTO ppu_quota_usage"
                "  (id, tenant_id, inference_name, billing_month, monthly_quota_snap,"
                "   units_used, tier_id, cost_accum)"
                " VALUES"
                "  (gen_random_uuid(), :tenant_id, :inference_name, :billing_month, :snap,"
                "   0, :tier_id, :cost_accum)"
                " ON CONFLICT (tenant_id, inference_name, billing_month, tier_id) DO NOTHING"
            ),
            {
                "tenant_id": tenant_id,
                "inference_name": row.inference_name,
                "billing_month": billing_month,
                "snap": monthly_quota,
                "tier_id": new_tier_id,
                "cost_accum": row.cost_accum,
            },
        )


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
    (ppu_quota_usage) keys on tier_id, so the old tier's row(s) stay as-is;
    new row(s) are seeded under the new tier via _carry_forward_quota_usage
    so units_used/cost_accum keep accumulating across the reassignment
    instead of appearing to reset.
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

    await _carry_forward_quota_usage(
        db, body.tenant_id, current.tier_id, new_tier.id, now.strftime("%Y-%m")
    )

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
