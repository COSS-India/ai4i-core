"""
ORM model for public.ef_feedback_reason ("ef_" = explicit feedback).

Configurable reason catalog backing GET /feedback/reasons (a map of task
type -> reasons). Ships with default rows out of the box; adding/editing a
reason is a data change, not a code change.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models import Base


class FeedbackReason(Base):
    __tablename__ = "ef_feedback_reason"
    __table_args__ = (
        UniqueConstraint("task_type", "code", name="uq_ef_feedback_reason_task_type_code"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Canonical task type. Indexed.
    task_type = Column(String(50), nullable=False, index=True)

    # Reason code, e.g. incorrect_meaning.
    code = Column(String(100), nullable=False)

    # Default (English) label - the string the API returns.
    label = Column(String(255), nullable=False)

    # Beyond spec: {lang: label} for interaction-language display.
    # v0.1: placeholder {"en": label}; localisation deferred.
    label_i18n = Column(JSONB, nullable=True)

    description = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, server_default="true")
    sort_order = Column(Integer, nullable=False, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<FeedbackReason id={self.id} task_type={self.task_type} code={self.code}>"