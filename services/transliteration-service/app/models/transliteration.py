"""
SQLAlchemy ORM models for Transliteration database tables.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class TransliterationRequestDB(Base):
    """Transliteration request tracking table."""

    __tablename__ = "transliteration_requests"

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
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    text_length = Column(Integer, nullable=True)
    is_sentence_level = Column(Boolean, nullable=False, default=True)
    num_suggestions = Column(Integer, nullable=True, default=0)
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
        "TransliterationResultDB",
        back_populates="request",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<TransliterationRequestDB(id={self.id}, model_id={self.model_id}, status={self.status})>"


class TransliterationResultDB(Base):
    """Transliteration result table."""

    __tablename__ = "transliteration_results"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transliteration_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    transliterated_text = Column(JSON, nullable=False)
    source_text = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    request = relationship("TransliterationRequestDB", back_populates="results")

    def __repr__(self) -> str:
        return f"<TransliterationResultDB(id={self.id}, request_id={self.request_id})>"
