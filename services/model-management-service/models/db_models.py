import uuid
from sqlalchemy import Column, String,BigInteger, Text, DateTime, ForeignKey , Boolean, UniqueConstraint, Enum as SQLEnum, and_
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, foreign
from sqlalchemy.sql import func
from db_connection import AppDBBase
import enum


class VersionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class ExperimentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Model(AppDBBase):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint('name', 'version', name='uq_name_version'),
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(String(255), nullable=False)  # Removed unique=True, now part of composite key
    version = Column(String(100), nullable=False)
    version_status = Column(SQLEnum(VersionStatus, name='version_status'), nullable=False, default=VersionStatus.ACTIVE)
    version_status_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    submitted_on = Column(BigInteger, nullable=False)
    updated_on = Column(BigInteger, nullable=True)
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
    created_by = Column(String(255), nullable=True) 
    updated_by = Column(String(255), nullable=True)  
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    services = relationship(
        "Service",
        back_populates="model",
        primaryjoin="and_(Model.model_id == foreign(Service.model_id), Model.version == foreign(Service.model_version))"
    )


class Service(AppDBBase):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint('model_id', 'model_version', 'name', name='uq_model_id_version_service_name'),
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(String(255), unique=True, nullable=False)  # Hash of (model_name, model_version, service_name)
    name = Column(String(255), nullable=False)
    service_description = Column(Text)
    hardware_description = Column(Text)
    published_on = Column(BigInteger, nullable=False)
    model_id = Column(String(255), nullable=False)  # Part of composite foreign key
    model_version = Column(String(100), nullable=False)  # Part of composite foreign key
    endpoint = Column(String(500), nullable=False)
    api_key = Column(String(255))
    health_status = Column(JSONB)
    benchmarks = Column(JSONB)
    is_published = Column(Boolean, nullable=False, default=False)
    published_at = Column(BigInteger, default=None)
    unpublished_at = Column(BigInteger, default=None)
    created_by = Column(String(255), nullable=True)  
    updated_by = Column(String(255), nullable=True) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    # Note: Foreign key constraint on composite (model_id, version) will be handled at application level
    model = relationship(
        "Model",
        back_populates="services",
        primaryjoin="and_(foreign(Service.model_id) == Model.model_id, foreign(Service.model_version) == Model.version)",
        foreign_keys=[model_id, model_version],
        uselist=False
    )
    # A/B Testing relationships
    experiment_variants = relationship("ExperimentVariant", back_populates="service", cascade="all, delete-orphan")


class Experiment(AppDBBase):
    __tablename__ = "experiments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(SQLEnum(ExperimentStatus, name='experiment_status'), nullable=False, default=ExperimentStatus.DRAFT)
    
    # Filters for experiment scope
    task_type = Column(JSONB, nullable=True)  # List of task types (e.g., ["asr", "tts"])
    languages = Column(JSONB, nullable=True)  # List of language codes (e.g., ["hi", "en"])
    
    # Duration limits
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    variants = relationship("ExperimentVariant", back_populates="experiment", cascade="all, delete-orphan", order_by="ExperimentVariant.traffic_percentage")


class ExperimentVariant(AppDBBase):
    __tablename__ = "experiment_variants"
    __table_args__ = (
        UniqueConstraint('experiment_id', 'service_id', name='uq_experiment_service'),
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id = Column(UUID(as_uuid=True), ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False)
    variant_name = Column(String(255), nullable=False)  # e.g., "control", "variant-a", "variant-b"
    
    # Reference to service (model + version combination)
    service_id = Column(String(255), ForeignKey('services.service_id', ondelete='CASCADE'), nullable=False)
    
    # Traffic distribution (percentage, 0-100)
    traffic_percentage = Column(BigInteger, nullable=False)  # Stored as integer (0-100)
    
    # Metadata
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    experiment = relationship("Experiment", back_populates="variants")
    service = relationship("Service", back_populates="experiment_variants")


class ExperimentMetrics(AppDBBase):
    __tablename__ = "experiment_metrics"
    __table_args__ = (
        UniqueConstraint('experiment_id', 'variant_id', 'metric_date', name='uq_experiment_variant_date'),
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id = Column(UUID(as_uuid=True), ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False)
    variant_id = Column(UUID(as_uuid=True), ForeignKey('experiment_variants.id', ondelete='CASCADE'), nullable=False)
    
    # Metrics
    request_count = Column(BigInteger, nullable=False, default=0)
    success_count = Column(BigInteger, nullable=False, default=0)
    error_count = Column(BigInteger, nullable=False, default=0)
    avg_latency_ms = Column(BigInteger, nullable=True)  # Average latency in milliseconds

    # Additional metrics (stored as JSONB for flexibility)
    custom_metrics = Column(JSONB, nullable=True)
    
    # Time bucket (date for daily aggregation)
    metric_date = Column(DateTime(timezone=True), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    experiment = relationship("Experiment")
    variant = relationship("ExperimentVariant")

