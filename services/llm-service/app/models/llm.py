"""
SQLAlchemy ORM models for LLM database tables.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    DateTime,
    ForeignKey,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


# ---------------------------------------------------------------------------
# Read-only stubs for FK-referenced auth tables (managed by auth-service).
# ---------------------------------------------------------------------------
class UserRef(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True)


class APIKeyRef(Base):
    __tablename__ = "api_keys"
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True)


class SessionRef(Base):
    __tablename__ = "sessions"
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True)


# ---------------------------------------------------------------------------
# Service models
# ---------------------------------------------------------------------------
class LLMRequestDB(Base):
    """LLM request tracking table."""

    __tablename__ = "llm_requests"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    api_key_id = Column(
        Integer,
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id = Column(
        Integer,
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_id = Column(String(100), nullable=False)
    input_language = Column(String(10), nullable=True)
    output_language = Column(String(10), nullable=True)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    results = relationship(
        "LLMResultDB",
        back_populates="request",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<LLMRequestDB(id={self.id}, model_id={self.model_id}, status={self.status})>"


class LLMResultDB(Base):
    """LLM result table."""

    __tablename__ = "llm_results"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    output_text = Column(Text, nullable=False)
    source_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    request = relationship("LLMRequestDB", back_populates="results")

    def __repr__(self) -> str:
        return f"<LLMResultDB(id={self.id}, request_id={self.request_id})>"
