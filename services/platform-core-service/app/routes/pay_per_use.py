"""Tier Management and Tenant Assignment endpoints for Pay-Per-Use."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_auth_db, get_db
from app.schemas.common import SuccessResponse
from app.schemas.pay_per_use.tenant_assignment import (
    ReviseBudgetRequest,
    ReviseBudgetResponse,
    TierAssignRequest,
    TierAssignResponse,
    TierReassignRequest,
)
from app.schemas.pay_per_use.tier import TierCreate, TierOut, TierUpdate
from app.services.pay_per_use import tenant_assignment_service, tier_service
from ai4i_core.exceptions.responses import success_response
from app.core.config import settings


router = APIRouter(prefix="/pay-per-use", tags=["Tier Management"])


@router.get("/tiers")
async def list_tiers(
    task_types: Optional[str] = Query(
        None,
        description="Comma-separated model task type filter: nmt, llm, asr, tts, ocr, transliteration, ner, language-detection, speaker-diarization, audio-lang-detection, language-diarization",
    ),
    session: AsyncSession = Depends(get_db),
):
    return await tier_service.list_tiers(session, task_types=task_types)


@router.get("/tier", response_model=TierOut)
async def get_tier(
    tier_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    return await tier_service.get_tier_by_id(tier_id, session)


@router.post("/tier", response_model=TierOut, status_code=status.HTTP_201_CREATED)
async def create_tier(
    request: Request,
    body: TierCreate,
    session: AsyncSession = Depends(get_db),
):
    created_by = request.headers.get("X-User-Id")
    return await tier_service.create_tier(body, session, created_by=created_by)


@router.patch("/tier", response_model=TierOut)
async def update_tier(
    request: Request,
    body: TierUpdate,
    session: AsyncSession = Depends(get_db),
):
    updated_by = request.headers.get("X-User-Id")
    return await tier_service.update_tier(
        body,
        session,
        updated_by=updated_by,
        auth_service_url=settings.auth_service_url,
        http_client=request.app.state.http_client,
    )


@router.delete("/tier", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tier(
    tier_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    await tier_service.delete_tier(tier_id, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tenant/tier", response_model=SuccessResponse[List[TierAssignResponse]])
async def list_tenant_tiers(
    tier_id: Optional[str] = Query(None, description="Filter by tier UUID"),
    db: AsyncSession = Depends(get_db),
):
    """List all active PPU tenant-tier assignments, optionally filtered by tier_id."""
    data = await tenant_assignment_service.list_tenant_tiers(db, tier_id=tier_id)
    return success_response(data=data)


@router.patch("/tenant/budget", response_model=ReviseBudgetResponse)
async def revise_tenant_budget(
    request: Request,
    body: ReviseBudgetRequest,
    db: AsyncSession = Depends(get_db),
    auth_db: AsyncSession = Depends(get_auth_db),
):
    """Top-up or top-down a tenant's Budget by an amount, effective immediately.

    Validates that the tenant exists and is ACTIVE in the auth DB, matching
    assign_tenant_tier/reassign_tenant_tier below. action='top-up' adds
    amount to the current budget_limit and always succeeds once the tenant
    is found and active. action='top-down' subtracts it, and is rejected
    with 409 (nothing written) if the result would drop below cumulative
    spend to date, or 422 if it would go negative. A result exactly equal to
    cumulative spend is accepted and blocks the tenant's next request
    immediately. Does not change the tenant's Tier, Quota Limit, or Rate Limit.
    """
    user_id = request.headers.get("X-User-Id")
    return await tenant_assignment_service.revise_budget(
        body,
        db,
        auth_db,
        auth_service_url=settings.auth_service_url,
        http_client=request.app.state.http_client,
        user_id=user_id,
    )


@router.post("/tenant/tier", response_model=TierAssignResponse)
async def assign_tenant_tier(
    request: Request,
    body: TierAssignRequest,
    db: AsyncSession = Depends(get_db),
    auth_db: AsyncSession = Depends(get_auth_db),
):
    """Assign a PPU tier to a tenant.

    Validates that the tenant exists and is ACTIVE in the auth DB.
    Returns 409 if the tenant already has an active tier assignment.
    """
    user_id = request.headers.get("X-User-Id")
    return await tenant_assignment_service.assign_tier(
        body,
        db,
        auth_db,
        user_id,
        auth_service_url=settings.auth_service_url,
        http_client=request.app.state.http_client,
    )


@router.patch("/tenant/tier/reassign", response_model=TierAssignResponse)
async def reassign_tenant_tier(
    request: Request,
    body: TierReassignRequest,
    db: AsyncSession = Depends(get_db),
    auth_db: AsyncSession = Depends(get_auth_db),
):
    """Reassign a tenant's active PPU tier to a different tier, effective immediately.

    Validates that the tenant exists and is ACTIVE in the auth DB.
    Budget/available balance carry over unchanged from the previous assignment.
    Quota and cost tracking start fresh under the new tier for the remainder
    of the current assignment period. Any stale quota-exhausted flags from
    the previous tier are cleared so the tenant isn't left 429'd on a tier
    with headroom.
    """
    user_id = request.headers.get("X-User-Id")
    return await tenant_assignment_service.reassign_tier(
        body,
        db,
        auth_db,
        user_id,
        auth_service_url=settings.auth_service_url,
        http_client=request.app.state.http_client,
    )
