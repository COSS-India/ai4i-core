"""
Request/response schemas for services.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class ServiceCreate(BaseSchema):
    service_id: str = Field(..., max_length=255)
    name: str = Field(..., max_length=255)
    service_description: Optional[str] = None
    hardware_description: Optional[str] = None
    model_id: str = Field(..., max_length=255)
    model_version: str = Field(..., max_length=100)
    endpoint: str = Field(..., max_length=500)
    api_key: Optional[str] = Field(None, max_length=255)
    health_status: Optional[dict[str, Any]] = None
    benchmarks: Optional[dict[str, Any]] = None
    policy: Optional[dict[str, Any]] = None
    is_published: bool
    inference_server_type: str = Field("triton", max_length=32)
    ssl_verify: bool = True
    created_by: Optional[str] = Field(None, max_length=255)


class ServiceUpdate(BaseSchema):
    service_description: Optional[str] = None
    hardware_description: Optional[str] = None
    endpoint: Optional[str] = Field(None, max_length=500)
    api_key: Optional[str] = Field(None, max_length=255)
    health_status: Optional[dict[str, Any]] = None
    benchmarks: Optional[dict[str, Any]] = None
    policy: Optional[dict[str, Any]] = None
    is_published: Optional[bool] = None
    inference_server_type: Optional[str] = Field(None, max_length=32)
    ssl_verify: Optional[bool] = None
    updated_by: Optional[str] = Field(None, max_length=255)


class ServiceResponse(BaseSchema):
    id: UUID
    service_id: str
    name: str
    service_description: Optional[str] = None
    hardware_description: Optional[str] = None
    model_id: str
    model_version: str
    endpoint: str
    health_status: Optional[dict[str, Any]] = None
    benchmarks: Optional[dict[str, Any]] = None
    policy: Optional[dict[str, Any]] = None
    is_published: bool
    published_at: Optional[datetime] = None
    unpublished_at: Optional[datetime] = None
    inference_server_type: str
    ssl_verify: bool
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ServiceListResponse(BaseSchema):
    id: UUID
    service_id: str
    name: str
    model_id: str
    model_version: str
    is_published: bool
    inference_server_type: str
    created_at: datetime
