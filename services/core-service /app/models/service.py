"""
ORM model for mm_services table (ai4iplatform_core schema).
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class Service(Base):
    __tablename__ = "mm_services"
    __table_args__ = {"schema": "ai4iplatform_core"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    service_description = Column(Text, nullable=True)
    hardware_description = Column(Text, nullable=True)
    model_id = Column(
        String(255),
        ForeignKey("ai4iplatform_core.mm_models.model_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_version = Column(String(100), nullable=False)
    endpoint = Column(String(500), nullable=False)
    api_key = Column(String(255), nullable=True)
    health_status = Column(JSONB, nullable=True)
    benchmarks = Column(JSONB, nullable=True)
    policy = Column(JSONB, nullable=True)
    is_published = Column(Boolean, nullable=False)
    published_at = Column(DateTime(timezone=True), server_default=func.now())
    unpublished_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    inference_server_type = Column(String(32), nullable=False, server_default="triton")
    ssl_verify = Column(Boolean, nullable=False, server_default="true")

    model = relationship("Model", back_populates="services", foreign_keys=[model_id])
