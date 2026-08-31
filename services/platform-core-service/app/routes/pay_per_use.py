"""Tier Management endpoints for Pay-Per-Use.

Tenant-tier-assignment and tenant-budget endpoints that used to live here
(POST/PATCH /tenant/tier[, /reassign], GET /tenant/tier, PATCH
/tenant/budget) have moved to auth-service (PATCH /auth/tenants/{id}/tier,
GET /auth/tenants/tier/list, PATCH /auth/tenants/{id}/budget) — tier and
budget now live directly on auth-service's tenants table, so tenant-scoped
PPU assignment is no longer a platform-core-service concern. See
tenant_assignment_service.py's removal in the same change.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.pay_per_use.tier import ListTiersResponse, TierCreate, TierOut, TierUpdate
from app.services.pay_per_use import tier_service
from app.core.config import settings


router = APIRouter(prefix="/pay-per-use", tags=["Tier Management"])


@router.get("/tiers", response_model=ListTiersResponse)
async def list_tiers(
    task_types: Optional[str] = Query(
        None,
        description="Comma-separated model task type filter: nmt, llm, asr, tts, ocr, transliteration, ner, language-detection, speaker-diarization, audio-lang-detection, language-diarization",
    ),
    session: AsyncSession = Depends(get_db),
):
    """List active PPU tiers, optionally filtered by task type."""
    return await tier_service.list_tiers(session, task_types=task_types)


@router.get("/tier", response_model=TierOut)
async def get_tier(
    tier_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    """Get a single PPU tier by id."""
    return await tier_service.get_tier_by_id(tier_id, session)


@router.post("/tier", response_model=TierOut, status_code=status.HTTP_201_CREATED)
async def create_tier(
    request: Request,
    body: TierCreate,
    session: AsyncSession = Depends(get_db),
):
    """Create a new PPU tier."""
    created_by = request.headers.get("X-User-Id")
    return await tier_service.create_tier(body, session, created_by=created_by)


@router.patch("/tier", response_model=TierOut)
async def update_tier(
    request: Request,
    body: TierUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Update an existing PPU tier."""
    updated_by = request.headers.get("X-User-Id")
    return await tier_service.update_tier(
        body,
        session,
        updated_by=updated_by,
        auth_service_url=settings.auth_service_url,
        http_client=request.app.state.http_client,
    )


@router.delete(
    "/tier",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={204: {"description": "Tier deleted successfully. No content is returned."}},
)
async def delete_tier(
    request: Request,
    tier_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    """Delete a PPU tier. Returns 204 No Content on success — a delete never
    has a response body."""
    await tier_service.delete_tier(
        tier_id,
        session,
        auth_service_url=settings.auth_service_url,
        http_client=request.app.state.http_client,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
