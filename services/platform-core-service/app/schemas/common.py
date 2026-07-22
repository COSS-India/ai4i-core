"""
Shared building-block schemas used by both Model and Service domains.
"""

import re
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import BaseSchema
from app.schemas.enums.model_management import (
    AudioFormatEnum,
    LicenseEnum,
    TaskTypeEnum,
    TextFormatEnum,
)

_T = TypeVar("_T")


class SuccessResponse(BaseModel, Generic[_T]):
    success: bool
    data: _T


# ── Shared regex for entity name format: alphanumeric, hyphen, slash ──
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9/-]+$")


def validate_entity_name(value: str, *, field: str = "name") -> str:
    """Common validator for model/service names."""
    if not value:
        raise ValueError(f"{field} is required")
    if not _NAME_PATTERN.match(value):
        raise ValueError(
            f"{field} must contain only alphanumeric characters, hyphens (-), "
            f"and forward slashes (/). Example: 'ai4bharat/indictrans-gpu'. "
            f"Got: '{value}'"
        )
    return value


class TaskSpec(BaseSchema):
    """Strict task type — used on input."""

    type: TaskTypeEnum

    @field_validator("type", mode="before")
    @classmethod
    def normalize_task_type(cls, v: Any) -> Any:
        if isinstance(v, TaskTypeEnum):
            return v.value
        if isinstance(v, str):
            v_normalized = v.lower()
            for member in TaskTypeEnum:
                if member.value.lower() == v_normalized:
                    return member.value
            valid = [m.value for m in TaskTypeEnum]
            raise ValueError(f"Invalid task type '{v}'. Valid types: {', '.join(valid)}")
        return v


class TaskSpecLenient(BaseSchema):
    """Lenient task type for response paths — tolerates legacy/invalid values in DB."""

    type: str

    @field_validator("type", mode="before")
    @classmethod
    def normalize_task_type(cls, v: Any) -> Any:
        if isinstance(v, TaskTypeEnum):
            return v.value
        if isinstance(v, str):
            v_normalized = v.lower()
            for member in TaskTypeEnum:
                if member.value.lower() == v_normalized:
                    return member.value
            return v
        return v


# ── Service-level inference endpoint (ULCA InferenceAPIEndPoint) ──
# The live, callable endpoint lives only on Service — Model no longer carries
# an inference_endpoint of its own (AI4IDS-2478 review: the concept belongs
# to the deployed Service, not the registered Model).


class TrainingDataset(BaseSchema):
    """Metadata about the dataset a service's underlying model was trained on."""

    datasetId: Optional[str] = None
    description: str


class InferenceApiKey(BaseSchema):
    name: str = "Authorization"
    value: str


class AsyncApiDetails(BaseSchema):
    pollingUrl: str
    pollInterval: int
    asyncApiSchema: Optional[Dict[str, Any]] = None
    asyncApiPollingSchema: Optional[Dict[str, Any]] = None


class AudioFormats(BaseSchema):
    audio: List[AudioFormatEnum]


class TextFormats(BaseSchema):
    text: List[TextFormatEnum]


class InferenceAPIEndPoint(BaseModel):
    """ULCA Service.inferenceEndPoint — how to actually invoke the deployed service.

    The ``schema`` JSON key is aliased to ``endpoint_schema`` in Python to
    avoid shadowing Pydantic v2's ``BaseModel.schema`` class method.
    ``adapterConfig`` is an AI4Bharat extension (not part of the ULCA spec)
    carrying the Triton tensor-mapping config for this deployment.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="allow")

    callbackUrl: str
    inferenceApiKey: Optional[InferenceApiKey] = None
    isMultilingualEnabled: bool = False
    supportedInputFormats: Optional[Union[AudioFormats, TextFormats]] = None
    supportedOutputFormats: Optional[Union[AudioFormats, TextFormats]] = None
    endpoint_schema: List[Dict[str, Any]] = Field(alias="schema")
    isSyncApi: Optional[bool] = None
    asyncApiDetails: Optional[AsyncApiDetails] = None
    providerName: Optional[str] = Field(None, min_length=5, max_length=100)
    serviceId: Optional[str] = Field(None, min_length=5, max_length=100)
    infraDescription: Optional[str] = Field(None, min_length=5, max_length=100)
    inferenceModelId: Optional[str] = Field(None, min_length=5, max_length=100)
    adapter_config: Optional[Dict[str, Any]] = Field(None, alias="adapterConfig")


# ── Submitter / team ──


class OAuthId(BaseSchema):
    oauthId: str
    provider: str


class TeamMember(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="ignore")

    name: str
    aboutMe: Optional[str] = None
    oauthId: Optional[OAuthId] = None


class Submitter(BaseSchema):
    name: str
    aboutMe: Optional[str] = None
    team: List[TeamMember] = Field(default_factory=list)


# ── Benchmarks ──


class Score(BaseSchema):
    metricName: str
    score: str


class BenchmarkLanguage(BaseSchema):
    sourceLanguage: Optional[str] = None
    targetLanguage: Optional[str] = None


class Benchmark(BaseSchema):
    benchmarkId: str
    name: str
    description: str
    domain: str
    createdOn: str  # ISO datetime string
    languages: BenchmarkLanguage
    score: List[Score]


class BenchmarkEntry(BaseModel):
    """Performance benchmark entry attached to a service."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="ignore")

    output_length: Optional[int] = None
    generated: Optional[int] = None
    actual: Optional[int] = None
    throughput: Optional[int] = None
    p50: Optional[float] = Field(default=None, alias="50%")
    p99: Optional[float] = Field(default=None, alias="99%")
    language: Optional[str] = None


# ── License validator helper ──


def validate_license(value: Any) -> Any:
    """Normalize an incoming license string to a known LicenseEnum value."""
    if value is None:
        return value
    if isinstance(value, LicenseEnum):
        return value.value
    if isinstance(value, str):
        normalized = value.strip()
        for member in LicenseEnum:
            if member.value.lower() == normalized.lower():
                return member.value
        valid = [m.value for m in LicenseEnum]
        raise ValueError(f"Invalid license '{value}'. Valid licenses: {', '.join(valid)}")
    return value
