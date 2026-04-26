"""
ORM model for public.models table.
"""

import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class VersionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("model_id", name="uq_models_model_id"),
        UniqueConstraint("name", "version", name="uq_name_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(String(255), nullable=False, index=True)
    version = Column(String(100), nullable=False)
    version_status = Column(
        Enum(VersionStatus, name="version_status", values_callable=lambda x: [e.value for e in x]),
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
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    services = relationship("Service", back_populates="model", foreign_keys="Service.model_id")
