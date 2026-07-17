"""
Business-logic service for the Explicit Feedback API (v0.1 — thumbs up/down).

Owns the rules:
- reasons / comments / correctedOutput are accepted only when rating is
  NEGATIVE (thumbs-down); a POSITIVE submission carrying any of them is
  rejected outright rather than silently stripped.
- modelTaskType is canonicalised to the platform's internal TaskTypeEnum
  vocabulary; llm and unknown values are rejected by the Pydantic enum
  itself before this service ever runs.
- tenant is derived from the gateway-injected X-Tenant-Id header, never
  trusted from the request body (see FeedbackSubmission.tenantId).
- Anonymous/guest ("Try it now") submissions have tenant_id=None and are
  tagged feedback_source=PORTAL_TRY_IT_NOW; everything else is API.
- One feedback per requestId — a duplicate submission updates the existing
  row (FeedbackRepository.create_or_update), rather than erroring.
- Reason codes are NOT validated against a catalog yet: ef_feedback_reason
  (the configurable reason catalog) is a separate piece of work. Per the
  LLD, reasons are accepted as free strings until that table exists and is
  seeded — validation switches on there, not here.
"""

from app.core.exceptions import AppError
from app.models.feedback.feedback import Feedback
from app.repositories.feedback.feedback_repository import FeedbackRepository
from app.schemas.enums.feedback import FeedbackSourceEnum, RatingEnum, resolve_feedback_task_type
from app.schemas.feedback.feedback import FeedbackResponse, FeedbackSubmission


class FeedbackValidationError(AppError):
    """Feedback API request validation failure — 400 per the Feedback API
    spec (the platform's generic ValidationError maps to 422, which doesn't
    match this spec's documented contract)."""

    def __init__(self, message: str, code: str = "INVALID_REQUEST") -> None:
        super().__init__(message=message, code=code, status_code=400)


class FeedbackService:
    """Application-level service orchestrating feedback submission."""

    def __init__(self, feedback_repo: FeedbackRepository) -> None:
        self._feedback_repo = feedback_repo

    async def submit(
        self,
        payload: FeedbackSubmission,
        *,
        tenant_id: str | None,
        created_by: str | None,
    ) -> FeedbackResponse:
        model_task_type = resolve_feedback_task_type(payload.modelTaskType)

        is_negative = payload.rating == RatingEnum.NEGATIVE
        if not is_negative and (payload.reasons or payload.comments or payload.correctedOutput):
            raise FeedbackValidationError(
                "reasons, comments, and correctedOutput are only accepted when rating is NEGATIVE."
            )

        language_info = payload.languageInfo
        feedback_source = (
            FeedbackSourceEnum.PORTAL_TRY_IT_NOW if tenant_id is None else FeedbackSourceEnum.API
        )

        entity = Feedback(
            request_id=payload.requestId,
            model_task_type=model_task_type,
            feedback_type=payload.feedbackType,
            rating=payload.rating,
            reasons=payload.reasons,
            comments=payload.comments,
            corrected_output=payload.correctedOutput,
            model_provider=payload.modelProvider,
            model_version=payload.modelVersion,
            model_id=payload.modelId,
            tenant_id=tenant_id,
            source_language=language_info.sourceLanguage if language_info else None,
            target_language=language_info.targetLanguage if language_info else None,
            language_info=language_info.model_dump(exclude_none=True) if language_info else None,
            feedback_source=feedback_source.value,
            created_by=created_by,
        )
        saved = await self._feedback_repo.create_or_update(entity)

        return FeedbackResponse(
            status="SUCCESS",
            feedbackId=saved.id,
            message="Feedback recorded successfully.",
        )
