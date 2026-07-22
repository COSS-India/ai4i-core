"""
Shared building-block schemas used by both Model and Service domains.
"""

import re
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import BaseSchema
from app.schemas.enums.model_management import (
    LicenseEnum,
    OAuthProviderEnum,
    SupportedLanguagesEnum,
    SupportedScriptsEnum,
    TaskTypeEnum,
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


# ── Inference endpoint schema (model definition, not the live endpoint URL) ──


class InferenceApiKey(BaseModel):
    """Auth header expected by the model's callback URL (ULCA ``inferenceApiKey``)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="ignore")

    name: str = "Authorization"
    value: str


class AsyncApiDetails(BaseModel):
    """Polling details for async inference (ULCA ``AsyncApiDetails``).

    ``asyncApiSchema``/``asyncApiPollingSchema`` are task-specific request/
    response contracts validated by the inference service, so they stay a
    flexible passthrough here rather than a fully modeled discriminated union.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="ignore")

    pollingUrl: str
    pollInterval: int
    asyncApiSchema: Optional[Dict[str, Any]] = None
    asyncApiPollingSchema: Optional[Dict[str, Any]] = None


class InferenceEndPoint(BaseModel):
    """Model-level inference endpoint metadata (ULCA ``InferenceAPIEndPoint``).

    The ``schema`` JSON key is aliased to ``endpoint_schema`` in Python to
    avoid shadowing Pydantic v2's ``BaseModel.schema`` class method. Its
    task-specific request/response contract is validated by the inference
    service, not the model registry, so it stays a flexible passthrough dict
    here rather than a fully modeled discriminated union.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="allow")

    callbackUrl: str
    inferenceApiKey: Optional[InferenceApiKey] = None
    isMultilingualEnabled: bool = False
    endpoint_schema: Dict[str, Any] = Field(..., alias="schema")
    isSyncApi: Optional[bool] = None
    asyncApiDetails: Optional[AsyncApiDetails] = None
    adapter_config: Optional[Dict[str, Any]] = Field(None, alias="adapterConfig")


# ── Submitter / team ──


class OAuthId(BaseSchema):
    """OAuth identity of a contributor/submitter (ULCA ``OAuthIdentity``)."""

    identifier: Optional[str] = None
    oauthId: Optional[str] = None
    provider: Optional[OAuthProviderEnum] = None


class TeamMember(BaseModel):
    """A contributor on the submitter's team (ULCA ``Contributor``)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="ignore")

    name: str = Field(..., min_length=5, max_length=50)
    aboutMe: Optional[str] = None
    oauthId: Optional[OAuthId] = None


class Submitter(BaseSchema):
    """The model provider — who submitted this model (ULCA ``Submitter``)."""

    name: str = Field(..., min_length=3, max_length=50)
    oauthId: Optional[OAuthId] = None
    aboutMe: Optional[str] = None
    team: List[TeamMember] = Field(default_factory=list)


# ── Language ──


class LanguagePair(BaseSchema):
    """A language, or source/target language pair, a model supports (ULCA
    ``LanguagePair``). Leave ``targetLanguage`` unset to indicate a single
    language rather than a pair."""

    sourceLanguage: SupportedLanguagesEnum
    sourceLanguageName: Optional[str] = None
    sourceScriptCode: Optional[SupportedScriptsEnum] = None
    targetLanguage: Optional[SupportedLanguagesEnum] = None
    targetLanguageName: Optional[str] = None
    targetScriptCode: Optional[SupportedScriptsEnum] = None


# ── Training dataset ──


class TrainingDataset(BaseSchema):
    """Training dataset metadata used to train the model (ULCA ``TrainingDataset``)."""

    description: str
    datasetId: Optional[str] = None


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
