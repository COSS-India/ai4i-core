"""
ORM model for public.services table.

A Service is a deployed instance of a Model — identified by a user-supplied
`service_id` that must be globally unique. Service names are also globally
unique. A service can be in published or unpublished state; once published,
its model version becomes immutable until unpublished.

Services follow a soft-delete pattern: deletion sets `deleted_at` timestamp
but retains the record for audit and telemetry traceability. Soft-deleted
services are excluded from active queries and do not permit state transitions.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
        Index("ix_mm_services_deleted_at", "deleted_at"),
        Index("ix_mm_services_is_try_it_default", "is_try_it_default"),
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
    # ULCA InferenceAPIEndPoint alignment. `inference_api_key` is the new
    # canonical {name, value} shape; `api_key` above is kept only as a
    # deprecated legacy value (no dual-write, no backfill).
    inference_api_key = Column(JSONB, nullable=True)
    # ULCA's `schema` (InferenceSchemaArray) — required at the API layer on
    # new creates, nullable here since existing rows have none and are never
    # backfilled. Distinct from expected_response_schema below (that's a
    # live smoke-test fixture, this is a declared per-task contract).
    inference_schema = Column(JSONB, nullable=True)
    # Service owns its own sync/async-ness rather than inheriting the linked
    # Model's — two services wrapping the same model version can genuinely
    # differ here (e.g. dedicated-GPU sync tier vs. shared/queued async tier).
    is_sync_api = Column(Boolean, nullable=True)
    async_api_details = Column(JSONB, nullable=True)
    is_multilingual_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    supported_input_formats = Column(JSONB, nullable=True)
    supported_output_formats = Column(JSONB, nullable=True)
    provider_name = Column(String(100), nullable=True)
    inference_model_id = Column(String(100), nullable=True)
    health_status = Column(JSONB, nullable=True)
    benchmarks = Column(JSONB, nullable=True)
    # Sample of a correct response for this endpoint, supplied by the admin
    # at creation time and re-validated against on every endpoint change —
    # see app/utils/endpoint_validator.py's response-shape check.
    expected_response_schema = Column(JSONB, nullable=True)
    is_published = Column(Boolean, nullable=False, default=False, server_default="false")
    published_at = Column(DateTime(timezone=True), nullable=True)
    is_try_it_default = Column(Boolean, nullable=False, default=False, server_default="false")
    unpublished_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    task_type = Column(String(32), nullable=True)
    cost_per_unit = Column(Numeric(15, 8), nullable=True)
    unit_size = Column(BigInteger, nullable=True)
    unit_rate = Column(Numeric(15, 8), nullable=True)
    tier_ids = Column(ARRAY(String), nullable=True)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False,)

    model = relationship("Model", back_populates="services", foreign_keys=[model_id])
