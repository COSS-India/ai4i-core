"""
Database Models
SQLAlchemy ORM models for Feedback service database tables.
"""

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, BigInteger,
    func, text, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class FeedbackMetric(Base):
    """Unified feedback record for all AI service evaluations."""

    __tablename__ = "feedback_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Multi-tenancy
    organization = Column(String(100), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=True, index=True)

    # Trace & service identification
    trace_id = Column(String(255), unique=True, nullable=False, index=True)
    service_id = Column(String(100), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)   # nmt, asr, tts, ocr
    language = Column(String(50), nullable=True, index=True)

    # Content
    source_input = Column(Text, nullable=False)
    model_output = Column(Text, nullable=False)
    human_correction = Column(Text, nullable=True)

    # Explicit feedback
    feedback_source = Column(String(50), nullable=True)  # user, system, batch
    rating = Column(Integer, nullable=True)

    # Implicit telemetry
    implicit_score = Column(Integer, nullable=True, default=0)
    event_log = Column(JSONB, nullable=True, default=list)

    # AI evaluation
    ai_status = Column(String(50), nullable=False, default="PENDING")   # PENDING, PASS, FAIL, ERROR
    error_type = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=True)   # HIGH, MEDIUM, LOW
    payload = Column(JSONB, nullable=True, default=dict)  # ai_reasoning, ai_correction, comments

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_feedback_org_status", "organization", "ai_status"),
        Index("ix_feedback_org_task", "organization", "task_type"),
        Index("ix_feedback_created_desc", "created_at"),
    )
