"""SQLAlchemy ORM models for TTS database tables."""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


# ---------------------------------------------------------------------------
# Read-only stubs for FK-referenced auth tables (managed by auth-service).
# These let SQLAlchemy resolve ForeignKey targets without importing the full
# auth models.  Only the primary key column is needed.
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
class TTSRequestDB(Base):
    """TTS request database model."""
    __tablename__ = "tts_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    model_id = Column(String(100), nullable=False)
    voice_id = Column(String(50), nullable=False)
    language = Column(String(10), nullable=False)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    results = relationship("TTSResultDB", back_populates="request", cascade="all, delete-orphan")


class TTSResultDB(Base):
    """TTS result database model."""
    __tablename__ = "tts_results"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("tts_requests.id", ondelete="CASCADE"), nullable=False)
    audio_file_path = Column(Text, nullable=False)
    audio_duration = Column(Float, nullable=True)
    audio_format = Column(String(20), nullable=True)
    sample_rate = Column(Integer, nullable=True)
    bit_rate = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    request = relationship("TTSRequestDB", back_populates="results")
