"""
Pydantic request/response schemas for the Service domain.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema
from app.schemas.common import BenchmarkEntry, validate_entity_name
from app.schemas.enums import (
    InferenceServerTypeEnum,
    PolicyAccuracyEnum,
    PolicyCostEnum,
    PolicyLatencyEnum,
)
from app.schemas.model import ModelResponse


# ── Health & policy sub-schemas ──


class ServiceStatus(BaseSchema):
    status: Optional[str] = None
    lastUpdated: Optional[str] = None


class ServicePolicy(BaseSchema):
    """Latency/cost/accuracy SLA tiers — used for smart routing decisions."""

    latency: Optional[PolicyLatencyEnum] = None
    cost: Optional[PolicyCostEnum] = None
    accuracy: Optional[PolicyAccuracyEnum] = None


# ── Create / Update ──


class ServiceCreateRequest(BaseSchema):
    """Request body for POST /services."""

    name: str
    serviceDescription: str
    hardwareDescription: str
    modelId: str
    modelVersion: str
    endpoint: str
    api_key: Optional[str] = None
    inferenceServerType: InferenceServerTypeEnum = InferenceServerTypeEnum.triton
    sslVerify: bool = True
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    isPublished: Optional[bool] = False

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return validate_entity_name(v, field="Service name")

    @field_validator("inferenceServerType", mode="before")
    @classmethod
    def _normalize_server_type(cls, v: Any) -> Any:
        if v is None:
            return InferenceServerTypeEnum.triton.value
        if isinstance(v, InferenceServerTypeEnum):
            return v.value
        if isinstance(v, str):
            return v.strip().lower()
        return v


class ServiceUpdateRequest(BaseSchema):
    """Request body for PATCH /services. serviceId identifies the target.

    Note: name, modelId, modelVersion are NOT updatable; service_id is derived
    from service name only and is immutable.
    """

    serviceId: str
    serviceDescription: Optional[str] = None
    hardwareDescription: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    inferenceServerType: Optional[InferenceServerTypeEnum] = None
    sslVerify: Optional[bool] = None
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    isPublished: Optional[bool] = None

    @field_validator("inferenceServerType", mode="before")
    @classmethod
    def _normalize_server_type(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, InferenceServerTypeEnum):
            return v.value
        if isinstance(v, str):
            return v.strip().lower()
        return v


class ServiceHealthUpdateRequest(BaseSchema):
    """Request body for PATCH /services/{service_id}/health."""

    status: str


class ServicePolicyUpdateRequest(BaseSchema):
    """Request body for POST /services/{service_id}/policy."""

    policy: ServicePolicy


# ── Response ──


class ServiceResponse(BaseSchema):
    """Single service response (lightweight — no embedded model)."""

    serviceId: str
    uuid: str
    name: str
    serviceDescription: Optional[str] = None
    hardwareDescription: Optional[str] = None
    modelId: str
    modelVersion: str
    endpoint: Optional[str] = None
    inferenceServerType: str = InferenceServerTypeEnum.triton.value
    sslVerify: bool = True
    api_key: Optional[str] = None
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, Any]] = None
    policy: Optional[Dict[str, Any]] = None
    isPublished: bool = False
    publishedAt: Optional[str] = None
    unpublishedAt: Optional[str] = None
    createdBy: Optional[str] = None
    updatedBy: Optional[str] = None


class ServiceListItem(ServiceResponse):
    """List response item — augmented with the inline model snippet."""

    task: Optional[Dict[str, Any]] = None
    languages: List[Dict[str, Any]] = Field(default_factory=list)
    versionStatus: Optional[str] = None


class ServiceListResponse(BaseSchema):
    """Wrapped list with count and filter context."""

    items: List[ServiceListItem]
    total: int


class ServiceDetailResponse(ServiceResponse):
    """Full service view — includes embedded model card."""

    model: Optional[ModelResponse] = None


class ServicePolicyResponse(BaseSchema):
    """Response shape for /services/{service_id}/policy."""

    serviceId: str
    policy: Optional[Dict[str, Any]] = None


class ServicePolicyListResponse(BaseSchema):
    services: List[ServicePolicyResponse]
