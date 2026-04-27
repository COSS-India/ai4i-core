"""
ORM model for mm_models table (ai4iplatform_core schema).
"""

import enum

from sqlalchemy import Column, DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class VersionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class Model(Base):
    __tablename__ = "mm_models"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_mm_models_name_version"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    model_id = Column(String(255), nullable=False, unique=True, index=True)
    version = Column(String(100), nullable=False)
    version_status = Column(
        Enum(VersionStatus, name="version_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    version_status_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    ref_url = Column(String(500), nullable=True)
    task = Column(JSONB, nullable=False)
    languages = Column(JSONB, nullable=False)
    license = Column(String(255), nullable=True)
    domain = Column(JSONB, nullable=False)
    inference_endpoint = Column(JSONB, nullable=False)
    benchmarks = Column(JSONB, nullable=True)
    submitter = Column(JSONB, nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    services = relationship("Service", back_populates="model", foreign_keys="Service.model_id")
