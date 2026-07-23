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
- Reason codes (NEGATIVE only) are validated against the same effective
  catalog GET /feedback/reasons would return for that modelTaskType: active
  ef_feedback_reason rows if seeded, else the static CATALOG fallback in
  feedback_reasons_catalog.py. An unrecognised code is rejected (400).
- GET /feedback/reasons reads from ef_feedback_reason (the configurable
  catalog table) first; any task type with no active DB rows falls back to
  the static CATALOG in feedback_reasons_catalog.py (e.g. task types not yet
  seeded).
"""

from app.core.exceptions import AppError
from app.models.feedback.feedback import Feedback
from app.repositories.feedback.feedback_reason_repository import FeedbackReasonRepository
from app.repositories.feedback.feedback_repository import FeedbackRepository
from app.schemas.enums.feedback import (
    FeedbackSourceEnum,
    ModelTaskTypeEnum,
    RatingEnum,
    resolve_feedback_task_type,
)
from app.schemas.feedback.feedback import FeedbackResponse, FeedbackSubmission, Reason
from app.services.feedback.feedback_reasons_catalog import CATALOG


class FeedbackValidationError(AppError):
    """Feedback API request validation failure — 400 per the Feedback API
    spec (the platform's generic ValidationError maps to 422, which doesn't
    match this spec's documented contract)."""

    def __init__(self, message: str, code: str = "INVALID_REQUEST") -> None:
        super().__init__(message=message, code=code, status_code=400)


class FeedbackService:
    """Application-level service orchestrating feedback submission."""

    def __init__(
        self,
        feedback_repo: FeedbackRepository,
        reason_repo: FeedbackReasonRepository,
    ) -> None:
        self._feedback_repo = feedback_repo
        self._reason_repo = reason_repo

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

        if is_negative and payload.reasons:
            valid_codes = await self._valid_reason_codes(payload.modelTaskType, model_task_type)
            invalid_codes = [code for code in payload.reasons if code not in valid_codes]
            if invalid_codes:
                raise FeedbackValidationError(
                    f"Reason code(s) {invalid_codes} are not valid for modelTaskType "
                    f"'{payload.modelTaskType.value}'."
                )

        language_info = payload.languageInfo or []
        # source_language/target_language are flattened single-value columns
        # for basic filtering — best-effort from the first pair when the
        # client submits the model's full multi-pair language capability.
        # The full list is never lost: it's preserved verbatim in language_info.
        first_pair = language_info[0] if language_info else None
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
            source_language=first_pair.sourceLanguage if first_pair else None,
            target_language=first_pair.targetLanguage if first_pair else None,
            language_info=(
                [li.model_dump(exclude_none=True) for li in language_info] or None
            ),
            feedback_source=feedback_source.value,
            created_by=created_by,
        )
        saved = await self._feedback_repo.create_or_update(entity)

        return FeedbackResponse(
            status="SUCCESS",
            feedbackId=saved.id,
            message="Feedback recorded successfully.",
        )

    async def get_reasons(
        self,
        task_types: list[ModelTaskTypeEnum] | None,
        lang: str | None,
    ) -> dict[str, list[Reason]]:
        """GET /feedback/reasons. task_types=None (or empty) returns the full
        catalog (one entry per ModelTaskTypeEnum); otherwise a map with one
        entry per requested task type.

        Each task type's reasons are read from ef_feedback_reason (active
        rows, ordered by sort_order) first; a task type with no active DB
        rows falls back to the static CATALOG in feedback_reasons_catalog.py
        (e.g. task types not yet seeded). lang, when given, selects the
        matching translation from a DB row's label_i18n, falling back to
        the row's default label if that language isn't present.
        """
        task_types = task_types if task_types else list(ModelTaskTypeEnum)
        internal_task_types = [resolve_feedback_task_type(t) for t in task_types]
        rows = await self._reason_repo.get_by_task_type_with_language(internal_task_types, lang)

        rows_by_task_type: dict[str, list] = {}
        for row in rows:
            rows_by_task_type.setdefault(row.task_type, []).append(row)

        return {
            t.value: (
                self._to_reasons(rows_by_task_type[resolve_feedback_task_type(t)])
                if rows_by_task_type.get(resolve_feedback_task_type(t))
                else CATALOG[t]
            )
            for t in task_types
        }

    @staticmethod
    def _to_reasons(rows: list) -> list[Reason]:
        return [Reason(code=row.code, label=row.label) for row in rows]

    async def _valid_reason_codes(
        self, model_task_type: ModelTaskTypeEnum, internal_task_type: str
    ) -> set[str]:
        """The set of reason codes accepted for one modelTaskType — active
        ef_feedback_reason rows if seeded, else the static CATALOG fallback.
        Same source GET /feedback/reasons reads from, so a code POST /feedback
        rejects is never one GET /feedback/reasons would have offered."""
        rows = await self._reason_repo.get_by_task_type_with_language(
            [internal_task_type], lang=None
        )
        if rows:
            return {row.code for row in rows}
        return {reason.code for reason in CATALOG[model_task_type]}
