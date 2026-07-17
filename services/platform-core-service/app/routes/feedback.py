"""
Explicit Feedback API endpoints (v0.1 — thumbs up/down only).
"""

import logging

from fastapi import APIRouter, Depends, Request

from app.dependencies.services import FeedbackService, get_feedback_service
from app.schemas.feedback.feedback import FeedbackResponse, FeedbackSubmission

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
