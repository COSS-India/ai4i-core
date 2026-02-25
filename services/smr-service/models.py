"""
Database models and enums for SMR service.
These are copied from model-management-service to enable direct DB access.
"""
import uuid
from sqlalchemy import Column, String, BigInteger, Text, DateTime, Boolean, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, foreign
from sqlalchemy.sql import func
from db_connection import AppDBBase
import enum


class VersionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class TaskTypeEnum(str, enum.Enum):
    nmt = "nmt"
    tts = "tts"
    asr = "asr"
    llm = "llm"
    transliteration = "transliteration"
    language_detection = "language-detection"
    speaker_diarization = "speaker-diarization"
    audio_lang_detection = "audio-lang-detection"
    language_diarization = "language-diarization"
    ocr = "ocr"
    ner = "ner"


class Model(AppDBBase):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint('name', 'version', name='uq_name_version'),
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(String(255), nullable=False)
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
    service_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    service_description = Column(Text)
    hardware_description = Column(Text)
    published_on = Column(BigInteger, nullable=False)
    model_id = Column(String(255), nullable=False)
    model_version = Column(String(100), nullable=False)
    endpoint = Column(String(500), nullable=False)
    api_key = Column(String(255))
    health_status = Column(JSONB)
    benchmarks = Column(JSONB)
    policy = Column(JSONB)
    is_published = Column(Boolean, nullable=False, default=False)
    published_at = Column(BigInteger, default=None)
    unpublished_at = Column(BigInteger, default=None)
    created_by = Column(String(255), nullable=True)  
    updated_by = Column(String(255), nullable=True) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    model = relationship(
        "Model",
        back_populates="services",
        primaryjoin="and_(foreign(Service.model_id) == Model.model_id, foreign(Service.model_version) == Model.version)",
        foreign_keys=[model_id, model_version],
        uselist=False
    )
