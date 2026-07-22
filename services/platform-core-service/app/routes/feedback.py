"""
Explicit Feedback API endpoints (v0.1 — thumbs up/down only).
"""

import logging

from fastapi import APIRouter, Depends, Request

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
    taskType: ModelTaskTypeEnum | None = None,
    lang: str | None = None,
    svc: FeedbackService = Depends(get_feedback_service),
) -> dict[str, list[Reason]]:
    """
    Returns the reason catalog the UI renders on thumbs down: a map of task
    type to its active reasons. Omit taskType to get every task type.

    lang is reserved for localised labels — v0.1 returns English regardless
    of value; localisation is deferred.
    """
    return svc.get_reasons(taskType)
