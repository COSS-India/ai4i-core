"""
Pydantic request/response schemas for the Model domain.

API contract preserves the existing camelCase keys used by the deprecated
model-management-service so that consumers (gateway, frontends) do not break
during migration.
"""

from typing import Any, List, Optional

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema
from app.schemas.common import (
    Benchmark,
    InferenceEndPoint,
    InferenceEndPointPatch,
    LanguagePair,
    Submitter,
    TaskSpec,
    TaskSpecLenient,
    TrainingDataset,
    validate_entity_name,
    validate_license,
)
from app.schemas.enums.model_management import DomainEnum, VersionStatusEnum


# ── Create / Update ──


class ModelCreateRequest(BaseSchema):
    """Request body for POST /models."""

    version: str = Field(..., min_length=1, max_length=20)
    versionStatus: Optional[VersionStatusEnum] = VersionStatusEnum.ACTIVE
    submittedOn: Optional[int] = None  # Auto-generated server-side
    updatedOn: Optional[int] = None
    name: str = Field(..., min_length=5, max_length=100)
    description: str = Field(..., min_length=25, max_length=1000)
    refUrl: Optional[str] = Field(None, min_length=5, max_length=200)
    task: TaskSpec
    languages: Optional[List[LanguagePair]] = None
    isLangDetectionEnabled: bool = False
    isMultilingual: bool = False
    license: str
    licenseUrl: Optional[str] = Field(None, max_length=500)
    domain: List[DomainEnum]
    inferenceEndPoint: InferenceEndPoint
    benchmarks: List[Benchmark] = Field(default_factory=list)
    submitter: Submitter
    trainingDataset: TrainingDataset
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
    version: Optional[str] = Field(None, min_length=1, max_length=20)
    versionStatus: Optional[VersionStatusEnum] = None
    description: Optional[str] = Field(None, min_length=25, max_length=1000)
    refUrl: Optional[str] = Field(None, min_length=5, max_length=200)
    task: Optional[TaskSpec] = None
    languages: Optional[List[LanguagePair]] = None
    isLangDetectionEnabled: Optional[bool] = None
    isMultilingual: Optional[bool] = None
    license: Optional[str] = None
    licenseUrl: Optional[str] = Field(None, max_length=500)
    domain: Optional[List[DomainEnum]] = None
    inferenceEndPoint: Optional[InferenceEndPointPatch] = None
    benchmarks: Optional[List[Benchmark]] = None
    submitter: Optional[Submitter] = None
    trainingDataset: Optional[TrainingDataset] = None
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
    languages: List[LanguagePair] = Field(default_factory=list)
    isLangDetectionEnabled: bool = False
    isMultilingual: bool = False
    domain: List[str] = Field(default_factory=list)
    submitter: Optional[Submitter] = None
    license: Optional[str] = None
    licenseUrl: Optional[str] = None
    inferenceEndPoint: Optional[InferenceEndPoint] = None
    source: Optional[str] = None  # alias for refUrl
    task: TaskSpecLenient
    trainingDataset: Optional[TrainingDataset] = None
    classInstance: Optional[str] = None
    createdBy: Optional[str] = None
    updatedBy: Optional[str] = None


class ModelListItem(ModelResponse):
    """One row in a list response — same shape as ModelResponse for now."""


class ModelListResponse(BaseSchema):
    """Wrapped list response so we can attach metadata (count, filters)."""

    items: List[ModelListItem]
    total: int
