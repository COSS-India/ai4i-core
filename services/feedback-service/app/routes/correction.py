"""
Human correction and override routes.

All endpoints require ADMIN role JWT.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.dependencies.auth import AdminRequired
from app.models.feedback import FeedbackMetric
from app.schemas.feedback import FeedbackResponse, HumanCorrectionRequest, OverridePassRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/feedback",
    tags=["Corrections"],
    dependencies=[Depends(AdminRequired)],
)

get_db = get_tenant_db_session_factory()


@router.post("/human_correction", response_model=FeedbackResponse)
async def submit_human_correction(
    body: HumanCorrectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save a human-corrected output, creating a golden training pair.

    The record payload is updated with the correction to produce
    (source, rejected=model_output, chosen=human_correction) triples
    for downstream RLHF fine-tuning.
    """
    result = await db.execute(
        select(FeedbackMetric).where(FeedbackMetric.trace_id == body.trace_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")

    record.human_correction = body.corrected_output
    payload = dict(record.payload or {})
    payload["golden_pair"] = {
        "source": record.source_input,
        "rejected": record.model_output,
        "chosen": body.corrected_output,
    }
    record.payload = payload
    await db.commit()
    await db.refresh(record)

    return FeedbackResponse(
        id=record.id,
        trace_id=record.trace_id,
        ai_status=record.ai_status,
        message="Human correction saved. Golden pair created.",
    )


@router.post("/override_pass", response_model=FeedbackResponse)
async def override_to_pass(
    body: OverridePassRequest,
    db: AsyncSession = Depends(get_db),
):
    """Override a false-positive FAIL to PASS with an optional reason."""
    result = await db.execute(
        select(FeedbackMetric).where(FeedbackMetric.trace_id == body.trace_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    if record.ai_status != "FAIL":
        raise HTTPException(
            status_code=400,
            detail=f"Record is '{record.ai_status}', not FAIL. Cannot override.",
        )

    record.ai_status = "PASS"
    payload = dict(record.payload or {})
    payload["override_reason"] = body.reason or "Manual override by admin."
    record.payload = payload
    await db.commit()
    await db.refresh(record)

    return FeedbackResponse(
        id=record.id,
        trace_id=record.trace_id,
        ai_status=record.ai_status,
        message="Record overridden to PASS.",
    )
