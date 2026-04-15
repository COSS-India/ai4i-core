"""
Batch evaluation routes.

All endpoints require ADMIN role JWT.
"""

import logging
import uuid as uuid_lib

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.dependencies.auth import AdminRequired
from app.models.feedback import FeedbackMetric
from app.schemas.feedback import BatchProcessRequest, BatchProcessResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/feedback",
    tags=["Evaluation"],
    dependencies=[Depends(AdminRequired)],
)

get_db = get_tenant_db_session_factory()


def _org_from_request(request: Request) -> str:
    return getattr(request.state, "tenant_id", None) or "default"


@router.post("/batch_process", response_model=BatchProcessResponse)
async def batch_process(
    body: BatchProcessRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Queue a batch of items for async parallel LLM evaluation."""
    organization = _org_from_request(request)
    record_ids = []

    for item in body.items:
        result = await db.execute(
            select(FeedbackMetric).where(FeedbackMetric.trace_id == item.trace_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            record_ids.append(str(existing.id))
            continue

        record = FeedbackMetric(
            id=uuid_lib.uuid4(),
            organization=organization,
            tenant_id=getattr(request.state, "tenant_id", None),
            trace_id=item.trace_id,
            service_id=item.service_id,
            task_type=item.task_type,
            language=item.language,
            source_input=item.source_input,
            model_output=item.model_output,
            feedback_source="batch",
            ai_status="PENDING",
            implicit_score=0,
            event_log=[],
            payload={},
        )
        db.add(record)
        record_ids.append(str(record.id))

    await db.flush()
    await db.commit()

    db_session_factory = request.app.state.db_session_factory
    background_tasks.add_task(_bg_batch_evaluate, record_ids, db_session_factory)

    return BatchProcessResponse(
        queued=len(record_ids),
        message=f"{len(record_ids)} item(s) queued for evaluation.",
    )


async def _bg_batch_evaluate_async(record_ids: list[str], db_session_factory) -> None:
    from app.services.evaluator import evaluate_batch
    async with db_session_factory() as db:
        result = await db.execute(
            select(FeedbackMetric).where(
                FeedbackMetric.id.in_([uuid_lib.UUID(rid) for rid in record_ids])
            )
        )
        records = result.scalars().all()
        await evaluate_batch(records, db)


def _bg_batch_evaluate(record_ids: list[str], db_session_factory) -> None:
    import asyncio
    asyncio.run(_bg_batch_evaluate_async(record_ids, db_session_factory))
