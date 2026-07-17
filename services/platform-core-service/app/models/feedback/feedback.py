"""
ORM model for public.ef_feedback ("ef_" = explicit feedback).

One row per feedback submission (thumbs up/down, v0.1). Persistent — not
time-limited; Bhashini / model providers analyse this data over time.
Every row is tagged to request_id + model_provider + model_version for
cross-version comparison. One feedback per request_id: a duplicate
submission updates the existing row (see FeedbackRepository.create_or_update).
"""

import uuid

from sqlalchemy import Column, DateTime, Enum, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models import Base
from app.schemas.enums.feedback import FeedbackTypeEnum, RatingEnum


class Feedback(Base):
    __tablename__ = "ef_feedback"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_ef_feedback_request_id"),
        Index("ix_ef_feedback_request_id", "request_id"),
        Index("ix_ef_feedback_model_task_type", "model_task_type"),
        Index("ix_ef_feedback_tenant_id", "tenant_id"),
        Index("ix_ef_feedback_provider_version", "model_provider", "model_version"),
        Index("ix_ef_feedback_task_type_created_at", "model_task_type", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # X-Correlation-ID from the original inference response.
    request_id = Column(UUID(as_uuid=True), nullable=False)

    # Canonical internal task-type value (TaskTypeEnum), never "llm".
    model_task_type = Column(String(50), nullable=False)

    feedback_type = Column(
        Enum(FeedbackTypeEnum, name="feedback_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    rating = Column(
        Enum(RatingEnum, name="feedback_rating", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # NEGATIVE-only detail — API-enforced, nullable because POSITIVE feedback
    # never populates these (see FeedbackService.submit).
    reasons = Column(JSONB, nullable=True)
    comments = Column(Text, nullable=True)
    corrected_output = Column(Text, nullable=True)

    model_provider = Column(String(255), nullable=False)
    model_version = Column(String(100), nullable=False)

    # Null for anonymous/guest ("Try it now") submissions.
    tenant_id = Column(String(255), nullable=True)

    source_language = Column(String(20), nullable=True)
    target_language = Column(String(20), nullable=True)
    language_info = Column(JSONB, nullable=True)

    # Beyond spec — language the feedback itself was authored in (not the
    # inference request's language pair). v0.1 doesn't populate this yet.
    feedback_language = Column(String(20), nullable=True)

    # Beyond spec — API / UI_COMPONENT / PORTAL_TRY_IT_NOW. Server-derived,
    # never client-supplied (see FeedbackSourceEnum).
    feedback_source = Column(String(30), nullable=False, server_default="API")

    # Beyond spec — soft link to mm_models.model_id. No FK: the Feedback API
    # must keep accepting feedback for a model that's since been removed.
    model_id = Column(String(255), nullable=True)

    # User id if authenticated (X-User-Id); null for anonymous.
    created_by = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} request_id={self.request_id} rating={self.rating}>"
