"""
Request/response schemas for mm_models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class VersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class ModelCreate(BaseSchema):
    model_id: str = Field(..., max_length=255)
    version: str = Field(..., max_length=100)
    version_status: VersionStatus
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    ref_url: Optional[str] = Field(None, max_length=500)
    task: dict[str, Any]
    languages: list[Any]
    license: Optional[str] = Field(None, max_length=255)
    domain: dict[str, Any]
    inference_endpoint: dict[str, Any]
    benchmarks: Optional[dict[str, Any]] = None
    submitter: dict[str, Any]
    created_by: Optional[str] = Field(None, max_length=255)


class ModelUpdate(BaseSchema):
    version_status: Optional[VersionStatus] = None
    description: Optional[str] = None
    ref_url: Optional[str] = Field(None, max_length=500)
    task: Optional[dict[str, Any]] = None
    languages: Optional[list[Any]] = None
    license: Optional[str] = Field(None, max_length=255)
    domain: Optional[dict[str, Any]] = None
    inference_endpoint: Optional[dict[str, Any]] = None
    benchmarks: Optional[dict[str, Any]] = None
    submitter: Optional[dict[str, Any]] = None
    updated_by: Optional[str] = Field(None, max_length=255)


class ModelResponse(BaseSchema):
    id: UUID
    model_id: str
    version: str
    version_status: VersionStatus
    version_status_updated_at: Optional[datetime] = None
    name: str
    description: Optional[str] = None
    ref_url: Optional[str] = None
    task: dict[str, Any]
    languages: list[Any]
    license: Optional[str] = None
    domain: dict[str, Any]
    inference_endpoint: dict[str, Any]
    benchmarks: Optional[dict[str, Any]] = None
    submitter: dict[str, Any]
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ModelListResponse(BaseSchema):
    id: UUID
    model_id: str
    version: str
    version_status: VersionStatus
    name: str
    license: Optional[str] = None
    created_at: datetime
