"""
Database Models
SQLAlchemy ORM models for database tables
"""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class LanguageDetectionRequestDB(Base):
    """Language Detection Request database model"""
    __tablename__ = "language_detection_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(Integer, nullable=True)  # No FK to avoid dependency
    model_id = Column(String(100), nullable=False)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("LanguageDetectionResultDB", back_populates="request", cascade="all, delete-orphan")


class LanguageDetectionResultDB(Base):
    """Language Detection Result database model"""
    __tablename__ = "language_detection_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("language_detection_requests.id", ondelete="CASCADE"), nullable=False)
    source_text = Column(Text, nullable=False)
    detected_language = Column(String(10), nullable=False)  # ISO 639-3 code (e.g., 'hin', 'eng')
    detected_script = Column(String(10), nullable=False)    # ISO 15924 code (e.g., 'Deva', 'Latn')
    confidence_score = Column(Float, nullable=False)
    language_name = Column(String(100), nullable=True)      # Full language name
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("LanguageDetectionRequestDB", back_populates="results")

