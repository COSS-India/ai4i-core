"""
Pydantic request/response schemas for the Service domain.
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator, model_validator

from app.schemas.base import BaseSchema
from app.schemas.common import BenchmarkEntry, validate_entity_name
from app.schemas.enums.model_management import (
    InferenceServerTypeEnum,
    PolicyAccuracyEnum,
    PolicyCostEnum,
    PolicyLatencyEnum,
    resolve_task_type,
)
from app.schemas.model_management.model import ModelResponse


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


SERVICE_ID_RE = re.compile(r"^(?=.*[a-zA-Z0-9])[a-zA-Z0-9/_-]+$")
SERVICE_ID_MAX_LEN = 500


def validate_service_id(v: str) -> str:
    """Validate a serviceId value. Raises ValueError on failure."""
    if not v or not v.strip():
        raise ValueError("serviceId must not be empty")
    if len(v) > SERVICE_ID_MAX_LEN:
        raise ValueError(
            f"serviceId must not exceed {SERVICE_ID_MAX_LEN} characters"
        )
    if not SERVICE_ID_RE.match(v):
        raise ValueError(
            "serviceId must contain only alphanumeric characters, /, -, or _ "
            "and include at least one alphanumeric character"
        )
    return v


class ServiceCreateRequest(BaseSchema):
    """Request body for POST /services."""

    serviceId: str
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
    taskType: str
    costPerUnit: float = Field(..., ge=0)
    unitSize: int
    tierIds: List[str] = Field(..., min_length=1)

    @field_validator("taskType")
    @classmethod
    def _validate_task_type(cls, v: str) -> str:
        return resolve_task_type(v)

    @field_validator("serviceId")
    @classmethod
    def _validate_service_id(cls, v: str) -> str:
        return validate_service_id(v)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return validate_entity_name(v, field="Service name")

    @field_validator("tierIds")
    @classmethod
    def _validate_tier_ids(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("tierIds must contain at least one tier ID")
        for tid in v:
            if not tid or not tid.strip():
                raise ValueError("Each tier ID must be a non-empty string")
        return v

    @field_validator("unitSize")
    @classmethod
    def _validate_unit_size(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("unitSize must be greater than 0")
        return v

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

    Note: name, modelId, modelVersion are NOT updatable. serviceId is not editable.
    """

    # A request touching only these is the publish/unpublish toggle and is
    # exempt from _BILLING_FIELDS_REQUIRED_TOGETHER (see AI4IDS-2524/2525/2526/
    # 2527 — requiring them unconditionally, including on this toggle, would
    # break that flow; see _require_billing_fields_on_substantive_edit below).
    _PUBLISH_ONLY_FIELDS = {"serviceId", "isPublished"}
    _BILLING_FIELDS_REQUIRED_TOGETHER = ("taskType", "costPerUnit", "unitSize", "tierIds")

    serviceId: str
    serviceDescription: Optional[str] = None
    hardwareDescription: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    inferenceServerType: Optional[InferenceServerTypeEnum] = None
    sslVerify: Optional[bool] = None
    healthStatus: Optional[str] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    isPublished: Optional[bool] = None
    policy: Optional[ServicePolicy] = None
    taskType: Optional[str] = None
    costPerUnit: Optional[float] = Field(None, ge=0)
    unitSize: Optional[int] = None
    tierIds: Optional[List[str]] = None

    @field_validator("taskType")
    @classmethod
    def _validate_task_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return resolve_task_type(v)

    @field_validator("unitSize")
    @classmethod
    def _validate_unit_size(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("unitSize must be greater than 0")
        return v

    @field_validator("tierIds")
    @classmethod
    def _validate_tier_ids(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        if not v:
            raise ValueError("tierIds must contain at least one tier ID")
        for tid in v:
            if not tid or not tid.strip():
                raise ValueError("Each tier ID must be a non-empty string")
        return v

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

    @model_validator(mode="after")
    def _require_billing_fields_on_substantive_edit(self) -> "ServiceUpdateRequest":
        """taskType/costPerUnit/unitSize/tierIds must be supplied together on
        any edit beyond the publish/unpublish toggle (AI4IDS-2524/2525/2526/2527).

        A request touching only serviceId/isPublished (the publish/unpublish
        action) is exempt — requiring these fields there too would 422 that
        flow, which sends only {serviceId, isPublished} by design.
        """
        if self.model_fields_set - self._PUBLISH_ONLY_FIELDS:
            missing = [
                f for f in self._BILLING_FIELDS_REQUIRED_TOGETHER
                if getattr(self, f) is None
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} must be provided together on any "
                    "update other than publish/unpublish."
                )
        return self


# ── Response ──


class ServiceResponse(BaseSchema):
    """Single service response (lightweight — no embedded model)."""

    serviceId: str
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
    taskType: Optional[str] = None
    costPerUnit: Optional[float] = None
    unitSize: Optional[int] = None
    unitRate: Optional[float] = None
    tierIds: Optional[List[str]] = None
    tierNames: Optional[List[str]] = None
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
