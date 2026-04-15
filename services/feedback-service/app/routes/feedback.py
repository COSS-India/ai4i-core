"""
Feedback ingestion routes.

All endpoints require ADMIN role JWT.
"""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.dependencies.auth import AdminRequired
from app.models.feedback import FeedbackMetric
from app.schemas.feedback import (
    FeedbackRequest,
    FeedbackResponse,
    FeedbackStatusResponse,
    ImplicitEventRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/feedback",
    tags=["Feedback"],
    dependencies=[Depends(AdminRequired)],
)

get_db = get_tenant_db_session_factory()


def _org_from_request(request: Request) -> str:
    return getattr(request.state, "tenant_id", None) or "default"


# ---------------------------------------------------------------------------
# Implicit telemetry event
# ---------------------------------------------------------------------------

@router.post("/event", response_model=FeedbackResponse)
async def ingest_implicit_event(
    body: ImplicitEventRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a telemetry event and accumulate implicit reward score.

    Triggers LLM evaluation when reward_score <= -0.5.
    Auto-marks PASS when reward_score >= 0.5.
    """
    organization = _org_from_request(request)

    result = await db.execute(
        select(FeedbackMetric).where(FeedbackMetric.trace_id == body.trace_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        if not body.source_input or not body.model_output:
            raise HTTPException(
                status_code=422,
                detail="source_input and model_output are required for new trace_ids.",
            )
        record = FeedbackMetric(
            id=uuid.uuid4(),
            organization=organization,
            tenant_id=getattr(request.state, "tenant_id", None),
            trace_id=body.trace_id,
            service_id=body.service_id,
            task_type=body.task_type,
            language=body.language,
            source_input=body.source_input,
            model_output=body.model_output,
            feedback_source="system",
            ai_status="PENDING",
            implicit_score=0,
            event_log=[],
            payload={},
        )
        db.add(record)

    # Accumulate implicit score
    current_score = record.implicit_score or 0
    new_score = current_score + int(body.reward_score * 100)
    record.implicit_score = new_score

    event_log = list(record.event_log or [])
    event_log.append({
        "action": body.action,
        "reward_score": body.reward_score,
        "metrics": body.metrics or {},
    })
    record.event_log = event_log

    # Threshold triggers
    if body.reward_score >= 0.5 and record.ai_status == "PENDING":
        record.ai_status = "PASS"
    elif body.reward_score <= -0.5 and record.ai_status == "PENDING":
        await db.flush()
        record_id = str(record.id)
        db_session_factory = request.app.state.db_session_factory
        background_tasks.add_task(
            _bg_evaluate, record_id, record.source_input, record.model_output,
            record.task_type, record.language or "unknown", db_session_factory,
        )

    await db.commit()
    await db.refresh(record)
    return FeedbackResponse(
        id=record.id,
        trace_id=record.trace_id,
        ai_status=record.ai_status,
        message="Event ingested.",
    )


# ---------------------------------------------------------------------------
# Explicit feedback
# ---------------------------------------------------------------------------

@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit explicit feedback with optional LLM evaluation trigger."""
    organization = _org_from_request(request)

    result = await db.execute(
        select(FeedbackMetric).where(FeedbackMetric.trace_id == body.trace_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="trace_id already exists.")

    record = FeedbackMetric(
        id=uuid.uuid4(),
        organization=organization,
        tenant_id=getattr(request.state, "tenant_id", None),
        trace_id=body.trace_id,
        service_id=body.service_id,
        task_type=body.task_type,
        language=body.language,
        source_input=body.source_input,
        model_output=body.model_output,
        feedback_source=body.feedback_source,
        rating=body.rating,
        ai_status="PENDING",
        implicit_score=0,
        event_log=[],
        payload={},
    )
    db.add(record)
    await db.flush()

    if body.trigger_evaluation:
        record_id = str(record.id)
        db_session_factory = request.app.state.db_session_factory
        background_tasks.add_task(
            _bg_evaluate, record_id, body.source_input, body.model_output,
            body.task_type, body.language or "unknown", db_session_factory,
        )

    await db.commit()
    await db.refresh(record)
    return FeedbackResponse(
        id=record.id,
        trace_id=record.trace_id,
        ai_status=record.ai_status,
        message="Feedback recorded." + (" Evaluation queued." if body.trigger_evaluation else ""),
    )


# ---------------------------------------------------------------------------
# Status query
# ---------------------------------------------------------------------------

@router.get("/status/{trace_id}", response_model=FeedbackStatusResponse)
async def get_status(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get evaluation status and AI reasoning for a trace."""
    result = await db.execute(
        select(FeedbackMetric).where(FeedbackMetric.trace_id == trace_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    return record


# ---------------------------------------------------------------------------
# Latest records
# ---------------------------------------------------------------------------

@router.get("/latest", response_model=list[FeedbackStatusResponse])
async def get_latest(
    limit: int = 100,
    organization: str | None = None,
    task_type: str | None = None,
    ai_status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Fetch latest feedback records with optional filters."""
    query = select(FeedbackMetric)
    if organization:
        query = query.where(FeedbackMetric.organization == organization)
    if task_type:
        query = query.where(FeedbackMetric.task_type == task_type)
    if ai_status:
        query = query.where(FeedbackMetric.ai_status == ai_status)
    query = query.order_by(FeedbackMetric.created_at.desc()).limit(min(limit, 1000))

    result = await db.execute(query)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Background helper — uses app.state.db_session_factory directly
# ---------------------------------------------------------------------------

async def _bg_evaluate_async(record_id: str, source: str, output: str,
                              task_type: str, language: str, db_session_factory) -> None:
    from app.services.evaluator import evaluate_single
    async with db_session_factory() as db:
        await evaluate_single(record_id, source, output, task_type, language, db)


def _bg_evaluate(record_id: str, source: str, output: str,
                 task_type: str, language: str, db_session_factory) -> None:
    import asyncio
    asyncio.run(_bg_evaluate_async(record_id, source, output, task_type, language, db_session_factory))
