"""
SQLAlchemy ORM models for database tables.

Maps to tables created in 08-ai-services-schema.sql.
"""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from uuid import UUID as UUIDType

# Create base class for all models
Base = declarative_base()


class ASRRequestDB(Base):
    """SQLAlchemy model for asr_requests table."""
    __tablename__ = "asr_requests"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    
    # Request metadata
    model_id = Column(String(100), nullable=False)
    language = Column(String(10), nullable=False)
    audio_duration = Column(Float, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("ASRResultDB", back_populates="request", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ASRRequestDB(id={self.id}, model_id={self.model_id}, status={self.status})>"


class ASRResultDB(Base):
    """SQLAlchemy model for asr_results table."""
    __tablename__ = "asr_results"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    
    # Foreign key
    request_id = Column(UUID(as_uuid=True), ForeignKey("asr_requests.id", ondelete="CASCADE"), nullable=False)
    
    # Result data
    transcript = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=True)
    word_timestamps = Column(JSON, nullable=True)  # Stores JSONB data
    language_detected = Column(String(10), nullable=True)
    audio_format = Column(String(20), nullable=True)
    sample_rate = Column(Integer, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("ASRRequestDB", back_populates="results")
    
    def __repr__(self):
        return f"<ASRResultDB(id={self.id}, request_id={self.request_id}, transcript_length={len(self.transcript) if self.transcript else 0})>"
