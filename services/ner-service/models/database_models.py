"""
SQLAlchemy ORM models for NER database tables.

These tables map to the AI services schema defined in
`infrastructure/postgres/08-ai-services-schema.sql`.
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
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class NERRequestDB(Base):
    """NER request tracking table."""

    __tablename__ = "ner_requests"

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Foreign keys
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

    # Request metadata
    model_id = Column(String(100), nullable=False)
    language = Column(String(10), nullable=False)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    results = relationship(
        "NERResultDB",
        back_populates="request",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - repr
        return f"<NERRequestDB(id={self.id}, model_id={self.model_id}, status={self.status})>"


class NERResultDB(Base):
    """NER result table for storing extracted entities."""

    __tablename__ = "ner_results"

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Foreign key
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ner_requests.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Result payload
    entities = Column(
        JSON,
        nullable=False,
        doc="JSON structure containing extracted entities and labels",
    )
    source_text = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationship back-reference
    request = relationship(
        "NERRequestDB",
        back_populates="results",
    )

    def __repr__(self) -> str:  # pragma: no cover - repr
        return f"<NERResultDB(id={self.id}, request_id={self.request_id})>"


