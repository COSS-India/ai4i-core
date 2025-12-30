"""
Database Models
SQLAlchemy ORM models for database tables
"""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class AudioLangDetectionRequestDB(Base):
    """Audio Language Detection Request database model"""
    __tablename__ = "audio_lang_detection_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    model_id = Column(String(100), nullable=False)
    audio_duration = Column(Float, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("AudioLangDetectionResultDB", back_populates="request", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AudioLangDetectionRequestDB(id={self.id}, model_id={self.model_id}, status={self.status})>"


class AudioLangDetectionResultDB(Base):
    """Audio Language Detection Result database model"""
    __tablename__ = "audio_lang_detection_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("audio_lang_detection_requests.id", ondelete="CASCADE"), nullable=False)
    language_code = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=True)
    all_scores = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("AudioLangDetectionRequestDB", back_populates="results")

    def __repr__(self):
        return f"<AudioLangDetectionResultDB(id={self.id}, request_id={self.request_id}, language_code={self.language_code})>"

