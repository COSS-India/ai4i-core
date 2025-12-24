import uuid
from sqlalchemy import Column, String,BigInteger, Text, DateTime, ForeignKey , Boolean, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db_connection import AppDBBase



class Model(AppDBBase):
    __tablename__ = "models"
    # __table_args__ = {'schema': DB_SCHEMA}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(String(255), nullable=False)  # Removed unique constraint
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
    is_published = Column(Boolean, nullable=False, default=False)
    published_at = Column(BigInteger, default=None)
    unpublished_at = Column(BigInteger, default=None)
    version_status = Column(String(50), nullable=False, default="active")  # "active" or "deprecated"
    release_notes = Column(Text, default=None)
    is_immutable = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Composite unique constraint on (model_id, version)
    __table_args__ = (
        UniqueConstraint('model_id', 'version', name='uq_model_id_version'),
        Index('idx_model_id_version', 'model_id', 'version'),
        Index('idx_model_id_version_status', 'model_id', 'version_status'),
    )
    
    # Relationships
    services = relationship("Service", back_populates="model")


class Service(AppDBBase):
    __tablename__ = "services"
    # __table_args__ = {'schema': DB_SCHEMA}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(String(255), unique=True, nullable=False)
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
    version_updated_at = Column(BigInteger, default=None)  # Track when service was last updated to use a different model version
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Composite foreign key constraint will be handled at application level
    # since SQLAlchemy doesn't directly support composite foreign keys
    # Index for efficient service lookups by model version
    __table_args__ = (
        Index('idx_service_model_version', 'model_id', 'model_version'),
    )
    
    # Relationships
    model = relationship("Model", back_populates="services", foreign_keys=[model_id], primaryjoin="and_(Service.model_id == Model.model_id, Service.model_version == Model.version)")

