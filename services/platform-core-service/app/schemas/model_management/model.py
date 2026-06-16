"""
Pydantic request/response schemas for the Model domain.

API contract preserves the existing camelCase keys used by the deprecated
model-management-service so that consumers (gateway, frontends) do not break
during migration.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema
from app.schemas.common import (
    Benchmark,
    InferenceEndPoint,
    Submitter,
    TaskSpec,
    TaskSpecLenient,
    validate_entity_name,
    validate_license,
)
from app.schemas.enums.model_management import VersionStatusEnum


# ── Create / Update ──


class ModelCreateRequest(BaseSchema):
    """Request body for POST /models."""

    version: str
    versionStatus: Optional[VersionStatusEnum] = VersionStatusEnum.ACTIVE
    submittedOn: Optional[int] = None  # Auto-generated server-side
    updatedOn: Optional[int] = None
    name: str
    description: str
    refUrl: str
    task: TaskSpec
    languages: List[Dict[str, Any]]
    license: str
    domain: List[str]
    inferenceEndPoint: InferenceEndPoint
    benchmarks: List[Benchmark] = Field(default_factory=list)
    submitter: Submitter
    classInstance: Optional[str] = None

    @field_validator("version", mode="before")
    @classmethod
    def _validate_version(cls, v: Any) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("Version is required and must be a non-empty string")
        if isinstance(v, str):
            return v.strip()
        return str(v)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return validate_entity_name(v, field="Model name")

    @field_validator("versionStatus", mode="before")
    @classmethod
    def _validate_version_status(cls, v: Any) -> Any:
        if v is not None and str(v).upper() == VersionStatusEnum.DEPRECATED.value:
            raise ValueError(
                "Models cannot be created with 'DEPRECATED' status. "
                "Newly created models must start in 'ACTIVE' status. "
                "Deprecation is only allowed as a lifecycle transition after creation."
            )
        return v

    @field_validator("license", mode="before")
    @classmethod
    def _validate_license(cls, v: Any) -> Any:
        if v is None or v == "":
            raise ValueError("License field is required")
        return validate_license(v)


class ModelUpdateRequest(BaseSchema):
    """Request body for PATCH /models. modelId + version identify the target."""

    modelId: str
    version: Optional[str] = None
    versionStatus: Optional[VersionStatusEnum] = None
    description: Optional[str] = None
    refUrl: Optional[str] = None
    task: Optional[TaskSpec] = None
    languages: Optional[List[Dict[str, Any]]] = None
    license: Optional[str] = None
    domain: Optional[List[str]] = None
    inferenceEndPoint: Optional[InferenceEndPoint] = None
    benchmarks: Optional[List[Benchmark]] = None
    submitter: Optional[Submitter] = None
    classInstance: Optional[str] = None

    @field_validator("license", mode="before")
    @classmethod
    def _validate_license(cls, v: Any) -> Any:
        return validate_license(v)


# ── View / Response ──


class ModelViewRequest(BaseSchema):
    """Optional body for POST /models/{model_id} — pinning a specific version."""

    version: Optional[str] = None


class ModelResponse(BaseSchema):
    """Single-model response shape (preserves model-management camelCase)."""

    modelId: str
    name: str
    version: str
    submittedOn: Optional[int] = None
    versionStatus: Optional[str] = None
    versionStatusUpdatedAt: Optional[str] = None
    description: Optional[str] = None
    languages: List[Dict[str, Any]] = Field(default_factory=list)
    domain: List[str] = Field(default_factory=list)
    submitter: Optional[Submitter] = None
    license: Optional[str] = None
    inferenceEndPoint: Optional[InferenceEndPoint] = None
    source: Optional[str] = None  # alias for refUrl
    task: TaskSpecLenient
    classInstance: Optional[str] = None
    createdBy: Optional[str] = None
    updatedBy: Optional[str] = None


class ModelListItem(ModelResponse):
    """One row in a list response — same shape as ModelResponse for now."""


class ModelListResponse(BaseSchema):
    """Wrapped list response so we can attach metadata (count, filters)."""

    items: List[ModelListItem]
    total: int
