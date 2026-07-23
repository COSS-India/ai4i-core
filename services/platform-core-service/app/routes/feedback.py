"""
Explicit Feedback API endpoints (v0.1 — thumbs up/down only).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.dependencies.services import FeedbackService, get_feedback_service
from app.schemas.enums.feedback import ModelTaskTypeEnum
from app.schemas.feedback.feedback import FeedbackResponse, FeedbackSubmission, Reason

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/feedback",
    tags=["Feedback"],
)


@router.post(
    "",
    status_code=201,
    response_model=FeedbackResponse,
    summary="Submit explicit feedback (thumbs up / down)",
)
async def submit_feedback(
    request: Request,
    payload: FeedbackSubmission,
    svc: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    """
    Submit thumbs up (POSITIVE) / thumbs down (NEGATIVE) feedback for one
    inference response. reasons/comments/correctedOutput are accepted only
    when rating is NEGATIVE. One feedback per requestId — a second
    submission for the same requestId updates the first.

    Anonymous/guest ("Try it now") submissions are allowed: omit auth and
    tenant_id is stored as null.
    """
    tenant_id = request.headers.get("X-Tenant-Id")
    created_by = request.headers.get("X-User-Id")
    return await svc.submit(payload, tenant_id=tenant_id, created_by=created_by)


@router.get(
    "/reasons",
    response_model=dict[str, list[Reason]],
    summary="Get configurable feedback reasons per task type",
)
async def get_feedback_reasons(
    task_type: list[str] | None = Query(
        None,
        description=(
            "One or more task types: repeat the param (?task_type=ASR&task_type=TTS) "
            "and/or comma-separate a single value (?task_type=ASR,TTS)."
        ),
    ),
    lang: str | None = None,
    svc: FeedbackService = Depends(get_feedback_service),
) -> dict[str, list[Reason]]:
    """
    Return the configurable feedback reasons, keyed by task type.

    task_type omitted returns every task type; otherwise a map with one
    entry per requested task type (accepts multiple values: repeated params
    and/or comma-separated). For each task type, active reasons are read
    from the ef_feedback_reason DB catalog first (ordered by sort_order); a
    task type with no active DB rows falls back to the static catalog in
    feedback_reasons_catalog.py. lang, when given, selects that language's
    translation from a DB row (falling back to its default label if the
    language isn't present) — it has no effect on catalog fallback entries,
    which are English-only.
    """
    task_types = _parse_task_types(task_type)
    return await svc.get_reasons(task_types, lang=lang)


def _parse_task_types(raw: list[str] | None) -> list[ModelTaskTypeEnum] | None:
    if not raw:
        return None
    codes = [code.strip() for part in raw for code in part.split(",") if code.strip()]
    try:
        return [ModelTaskTypeEnum(code) for code in codes]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid task_type value(s) in {raw!r}. Expected values from "
                f"{[t.value for t in ModelTaskTypeEnum]}."
            ),
        ) from exc
