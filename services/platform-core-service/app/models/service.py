"""
ORM model for public.services table.

A Service is a deployed instance of a Model — identified by a deterministic
`service_id` hash derived from the service name. Service names are globally
unique. A service can be in published or unpublished state; once published,
its model version becomes immutable until unpublished.
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint, Numeric,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models import Base


class Service(Base):
    __tablename__ = "mm_services"
    __table_args__ = (
        UniqueConstraint("service_id", name="uq_mm_services_service_id"),
        UniqueConstraint("name", name="uq_mm_services_name"),
        ForeignKeyConstraint(
            ["model_id"],
            ["mm_models.model_id"],
            name="fk_mm_services_model_id",
        ),
        Index("ix_mm_services_is_published", "is_published"),
        Index("ix_mm_services_created_by", "created_by"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    service_description = Column(Text, nullable=True)
    hardware_description = Column(Text, nullable=True)
    model_id = Column(String(255), nullable=False, index=True)
    model_version = Column(String(100), nullable=False)
    endpoint = Column(String(500), nullable=False)
    inference_server_type = Column(String(32), nullable=False, server_default="triton")
    ssl_verify = Column(Boolean, nullable=False, server_default="true")
    api_key = Column(String(255), nullable=True)
    health_status = Column(JSONB, nullable=True)
    benchmarks = Column(JSONB, nullable=True)
    policy = Column(JSONB, nullable=True)
    adapter_config = Column(JSONB, nullable=True)
    is_published = Column(Boolean, nullable=False, default=False, server_default="false")
    published_at = Column(DateTime(timezone=True), nullable=True)
    unpublished_at = Column(DateTime(timezone=True), nullable=True)
    cost_per_unit = Column(Numeric(10, 4), nullable=True)
    billing_unit_type = Column(String(32), nullable=True)
    tier = Column(String(20), nullable=True)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False,)

    model = relationship("Model", back_populates="services", foreign_keys=[model_id])
