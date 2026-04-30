"""
Database Models
SQLAlchemy ORM models for database tables
"""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class NMTRequestDB(Base):
    """NMT Request database model"""
    __tablename__ = "nmt_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    model_id = Column(String(100), nullable=False)
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("NMTResultDB", back_populates="request", cascade="all, delete-orphan")


class NMTResultDB(Base):
    """NMT Result database model"""
    __tablename__ = "nmt_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("nmt_requests.id", ondelete="CASCADE"), nullable=False)
    translated_text = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=True)
    source_text = Column(Text, nullable=True)
    language_detected = Column(String(10), nullable=True)
    word_alignments = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("NMTRequestDB", back_populates="results")
