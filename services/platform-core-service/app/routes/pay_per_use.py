"""Tier Management endpoints for Pay-Per-Use."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.pay_per_use.tier import TierCreate, TierOut, TierUpdate
from app.services.pay_per_use import tier_service

router = APIRouter(tags=["Tier Management"])


@router.get("/tiers")
async def list_tiers(
    modelTaskType: Optional[str] = Query(
        None,
        description="Filter by model task type: LLM, NMT, ASR, TTS, OCR, Pipeline, Transliteration, NER, Text LD, Speaker Diarization, Audio LD",
    ),
    session: AsyncSession = Depends(get_db),
):
    return await tier_service.list_tiers(session, model_task_type=modelTaskType)


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
    return await tier_service.update_tier(body, session, updated_by=updated_by)


@router.delete("/tier", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tier(
    tier_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    await tier_service.delete_tier(tier_id, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
