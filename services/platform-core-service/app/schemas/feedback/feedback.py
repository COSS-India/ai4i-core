"""
Pydantic request/response schemas for the Explicit Feedback API (v0.1).

camelCase keys per spec — fields are named in camelCase directly (no alias
generator), matching the model_management schema convention.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema
from app.schemas.enums.feedback import FeedbackTypeEnum, ModelTaskTypeEnum, RatingEnum


class LanguageInfo(BaseSchema):
    """Optional language context. NMT/Transliteration use both fields (a
    language pair); other content services use sourceLanguage only;
    detection/diarization omit it."""

    sourceLanguage: Optional[str] = None
    targetLanguage: Optional[str] = None


class FeedbackSubmission(BaseSchema):
    """POST /feedback request body."""

    requestId: UUID = Field(
        ..., description="The X-Correlation-ID returned on the original inference response."
    )
    modelTaskType: ModelTaskTypeEnum
    feedbackType: FeedbackTypeEnum
    rating: RatingEnum

    reasons: Optional[List[str]] = Field(
        None,
        description="Reason codes (multi-select). NEGATIVE only.",
    )
    comments: Optional[str] = Field(None, description="Free-text comment. NEGATIVE only.")
    correctedOutput: Optional[str] = Field(
        None, description="User-provided correction (text tasks only). NEGATIVE only."
    )

    modelProvider: str = Field(..., description="From the enriched inference response's model block.")
    modelVersion: str = Field(..., description="From the enriched inference response's model block.")
    modelId: Optional[str] = Field(
        None, description="Soft reference to the model id. Optional."
    )

    # Accepted for contract completeness, but NOT trusted: the service layer
    # always derives tenant from the gateway-injected X-Tenant-Id header
    # (same pattern as every other route's created_by/tenant handling in
    # this service) rather than a client-supplied body field, so a caller
    # can't attribute feedback to a tenant it doesn't belong to.
    tenantId: Optional[str] = Field(
        None, description="Ignored — tenant is derived from X-Tenant-Id server-side."
    )

    # A list rather than a single pair: for a bidirectional model (e.g. NMT
    # en<->hi), clients may want to submit the model's full declared
    # language capability (mirroring the inference response's model.language
    # list) rather than only the single pair actually used for this request.
    languageInfo: Optional[List[LanguageInfo]] = None


class FeedbackResponse(BaseSchema):
    """201 response body — same shape for every task type."""

    status: str = "SUCCESS"
    feedbackId: UUID
    message: str = "Feedback recorded successfully."
