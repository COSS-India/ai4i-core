import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, String, Boolean, Integer, BigInteger, Text, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db_connection import AppDBBase,DB_SCHEMA



class Model(AppDBBase):
    """Model model - replaces MongoDB 'model' collection"""
    __tablename__ = "models"
    # __table_args__ = {'schema': DB_SCHEMA}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(String(255), unique=True, nullable=False)
    version = Column(String(100), nullable=False)
    submitted_on = Column(BigInteger, nullable=False)
    updated_on = Column(BigInteger, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    ref_url = Column(String(500))
    task = Column(JSONB, nullable=False)
    languages = Column(JSONB, nullable=False, default=list)
    license = Column(String(255))
    domain = Column(JSONB, nullable=False, default=list)
    inference_endpoint = Column(JSONB, nullable=False)
    benchmarks = Column(JSONB)
    submitter = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    services = relationship("Service", back_populates="model")


class Service(AppDBBase):
    """Service model - replaces MongoDB 'service' collection"""
    __tablename__ = "services"
    # __table_args__ = {'schema': DB_SCHEMA}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    service_description = Column(Text)
    hardware_description = Column(Text)
    published_on = Column(BigInteger, nullable=False)
    model_id = Column(String(255), ForeignKey(f'models.model_id')) # ForeignKey(f'{DB_SCHEMA}.models.model_id')
    endpoint = Column(String(500), nullable=False)
    api_key = Column(String(255))
    health_status = Column(JSONB)
    benchmarks = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    model = relationship("Model", back_populates="services")

