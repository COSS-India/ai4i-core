"""
Batch evaluation route.

Admin calls POST /batch_process with a limit.  The service reads that many
completed NMT translations directly from the NMT database, creates
FeedbackMetric records for any not yet evaluated, and queues them for
async LLM evaluation — no source/translated text needs to be sent by the
caller.

All endpoints require ADMIN role JWT.
"""

import logging
import re
import uuid as uuid_lib

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_multi_tenant import get_tenant_db_session_factory

from app.dependencies.auth import AdminRequired
from app.models.feedback import FeedbackMetric
from app.schemas.feedback import BatchProcessRequest, BatchProcessResponse

logger = logging.getLogger(__name__)

# Allowlist for schema names — prevents SQL injection in SET search_path.
_SAFE_SCHEMA_RE = re.compile(r'^[a-z0-9_]+$')


def _validate_schema(schema_name: str | None) -> str | None:
    if schema_name is None:
        return None
    if _SAFE_SCHEMA_RE.match(schema_name):
        return schema_name
    logger.warning("Unsafe schema_name rejected: %r — skipping SET search_path", schema_name)
    return None


router = APIRouter(
    prefix="/api/v1/feedback",
    tags=["Evaluation"],
    dependencies=[Depends(AdminRequired)],
)

get_db = get_tenant_db_session_factory()


def _org_from_request(request: Request) -> str:
    """Derive organization from JWT email domain, distinct from tenant_id."""
    email: str = getattr(request.state, "email", None) or ""
    if "@" in email:
        return email.split("@", 1)[1].lower()
    return getattr(request.state, "tenant_id", None) or "default"


@router.post("/batch_process", response_model=BatchProcessResponse)
async def batch_process(
    body: BatchProcessRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Pull the last `limit` completed NMT translations from the NMT database
    and queue them for LLM evaluation.

    Records already present in feedback_metrics are skipped when
    skip_evaluated=True (default).
    """
    from app.services.nmt_reader import fetch_nmt_records

    organization = _org_from_request(request)
    tenant_id = getattr(request.state, "tenant_id", None)

    # --- 1. Fetch NMT records from the NMT DB ---
    try:
        nmt_rows = await fetch_nmt_records(limit=body.limit, offset=body.offset)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not nmt_rows:
        return BatchProcessResponse(
            queued=0,
            skipped=0,
            message="No completed NMT records found in the NMT database.",
        )

    # --- 2. Optionally filter out already-evaluated trace_ids ---
    candidate_ids = [row["trace_id"] for row in nmt_rows]
    existing_ids: set[str] = set()

    if body.skip_evaluated:
        result = await db.execute(
            select(FeedbackMetric.trace_id).where(
                FeedbackMetric.trace_id.in_(candidate_ids)
            )
        )
        existing_ids = {row[0] for row in result.all()}

    # --- 3. Create FeedbackMetric records for new entries ---
    record_ids: list[str] = []
    skipped = len(existing_ids)

    for row in nmt_rows:
        trace_id = row["trace_id"]

        if trace_id in existing_ids:
            continue

        # Build a human-readable language label for the LLM judge
        language = f"{row['source_language']} → {row['target_language']}"

        record = FeedbackMetric(
            id=uuid_lib.uuid4(),
            organization=organization,
            tenant_id=tenant_id,
            trace_id=trace_id,
            service_id=row.get("model_id") or "nmt-service",
            task_type="nmt",
            language=language,
            source_input=row["source_text"],
            model_output=row["translated_text"],
            feedback_source="batch",
            ai_status="PENDING",
            implicit_score=0,
            event_log=[],
            payload={},
        )
        db.add(record)
        record_ids.append(str(record.id))

    if not record_ids:
        return BatchProcessResponse(
            queued=0,
            skipped=skipped,
            message=f"All {skipped} fetched record(s) were already evaluated.",
        )

    await db.flush()
    await db.commit()

    # --- 4. Queue background LLM evaluation ---
    db_session_factory = request.app.state.db_session_factory
    schema_name = getattr(request.state, "tenant_schema", None)
    background_tasks.add_task(
        _bg_batch_evaluate, record_ids, db_session_factory, schema_name
    )

    return BatchProcessResponse(
        queued=len(record_ids),
        skipped=skipped,
        message=(
            f"{len(record_ids)} record(s) queued for LLM evaluation"
            + (f", {skipped} already evaluated and skipped." if skipped else ".")
        ),
    )


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

async def _bg_batch_evaluate_async(
    record_ids: list[str], db_session_factory, schema_name: str | None
) -> None:
    from app.services.evaluator import evaluate_batch
    safe_schema = _validate_schema(schema_name)
    async with db_session_factory() as db:
        if safe_schema:
            await db.execute(text(f'SET search_path TO "{safe_schema}", public'))
        result = await db.execute(
            select(FeedbackMetric).where(
                FeedbackMetric.id.in_([uuid_lib.UUID(rid) for rid in record_ids])
            )
        )
        records = result.scalars().all()
        await evaluate_batch(records, db)


def _bg_batch_evaluate(
    record_ids: list[str], db_session_factory, schema_name: str | None
) -> None:
    import asyncio
    asyncio.run(_bg_batch_evaluate_async(record_ids, db_session_factory, schema_name))
