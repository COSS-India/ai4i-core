"""
Feedback ingestion routes.

Ingestion endpoints (/event, POST /) require any valid JWT (AuthRequired)
so upstream inference services and end-users can post telemetry and feedback.

Query endpoints (/status/{trace_id}, /latest) require ADMIN role.
"""

import logging
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.dependencies.auth import AdminRequired, AuthRequired
from app.models.feedback import FeedbackMetric
from app.schemas.feedback import (
    FeedbackRequest,
    FeedbackResponse,
    FeedbackStatusResponse,
    ImplicitEventRequest,
)
from app.services.pii_client import redact_pair

logger = logging.getLogger(__name__)

# Allowlist for schema names — only lowercase letters, digits, underscores.
# Prevents SQL injection in `SET search_path TO "{schema_name}", public`.
_SAFE_SCHEMA_RE = re.compile(r'^[a-z0-9_]+$')


def _validate_schema(schema_name: str | None) -> str | None:
    """Return schema_name if safe, None otherwise (with a warning log)."""
    if schema_name is None:
        return None
    if _SAFE_SCHEMA_RE.match(schema_name):
        return schema_name
    logger.warning("Unsafe schema_name rejected: %r — skipping SET search_path", schema_name)
    return None


router = APIRouter(
    prefix="/api/v1/feedback",
    tags=["Feedback"],
)

get_db = get_tenant_db_session_factory()


def _org_from_request(request: Request) -> str:
    """
    Derive a stable organization identifier from the JWT claims.

    Uses the domain portion of the authenticated user's email (e.g. "company.com")
    so that organization is distinct from tenant_id (the technical tenant key).
    Falls back to tenant_id, then "default".
    """
    email: str = getattr(request.state, "email", None) or ""
    if "@" in email:
        return email.split("@", 1)[1].lower()
    return getattr(request.state, "tenant_id", None) or "default"


# ---------------------------------------------------------------------------
# Implicit telemetry event
# ---------------------------------------------------------------------------

@router.post("/event", response_model=FeedbackResponse, dependencies=[Depends(AuthRequired)])
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
        tenant_id = getattr(request.state, "tenant_id", None)
        safe_source, safe_output = await redact_pair(
            body.source_input, body.model_output, body.language, tenant_id
        )
        record = FeedbackMetric(
            id=uuid.uuid4(),
            organization=organization,
            tenant_id=tenant_id,
            trace_id=body.trace_id,
            service_id=body.service_id,
            task_type=body.task_type,
            language=body.language,
            source_input=safe_source,
            model_output=safe_output,
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
        schema_name = getattr(request.state, "tenant_schema", None)
        background_tasks.add_task(
            _bg_evaluate, record_id, record.source_input, record.model_output,
            record.task_type, record.language or "unknown", db_session_factory,
            schema_name,
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

@router.post("", response_model=FeedbackResponse, dependencies=[Depends(AuthRequired)])
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

    tenant_id = getattr(request.state, "tenant_id", None)
    safe_source, safe_output = await redact_pair(
        body.source_input, body.model_output, body.language, tenant_id
    )

    record = FeedbackMetric(
        id=uuid.uuid4(),
        organization=organization,
        tenant_id=tenant_id,
        trace_id=body.trace_id,
        service_id=body.service_id,
        task_type=body.task_type,
        language=body.language,
        source_input=safe_source,
        model_output=safe_output,
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
        schema_name = getattr(request.state, "tenant_schema", None)
        background_tasks.add_task(
            _bg_evaluate, record_id, body.source_input, body.model_output,
            body.task_type, body.language or "unknown", db_session_factory,
            schema_name,
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
# Status query (admin-only)
# ---------------------------------------------------------------------------

@router.get("/status/{trace_id}", response_model=FeedbackStatusResponse,
            dependencies=[Depends(AdminRequired)])
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
# Latest records (admin-only)
# ---------------------------------------------------------------------------

@router.get("/latest", response_model=list[FeedbackStatusResponse],
            dependencies=[Depends(AdminRequired)])
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
# Background helpers — use app.state.db_session_factory with tenant schema
# ---------------------------------------------------------------------------

async def _bg_evaluate_async(record_id: str, source: str, output: str,
                              task_type: str, language: str, db_session_factory,
                              schema_name: str | None) -> None:
    from app.services.evaluator import evaluate_single
    safe_schema = _validate_schema(schema_name)
    async with db_session_factory() as db:
        if safe_schema:
            await db.execute(text(f'SET search_path TO "{safe_schema}", public'))
        await evaluate_single(record_id, source, output, task_type, language, db)


def _bg_evaluate(record_id: str, source: str, output: str,
                 task_type: str, language: str, db_session_factory,
                 schema_name: str | None) -> None:
    import asyncio
    asyncio.run(_bg_evaluate_async(record_id, source, output, task_type, language,
                                   db_session_factory, schema_name))
