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


class Model(AppDBBase):
    __tablename__ = "models"
    # __table_args__ = {'schema': DB_SCHEMA}
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    # Note: Foreign key constraint on composite (model_id, version) will be handled at application level
    # since SQLAlchemy doesn't easily support composite foreign keys to composite unique constraints
    model = relationship(
        "Model",
        back_populates="services",
        primaryjoin="and_(foreign(Service.model_id) == Model.model_id, foreign(Service.model_version) == Model.version)",
        foreign_keys=[model_id, model_version],
        uselist=False
    )

