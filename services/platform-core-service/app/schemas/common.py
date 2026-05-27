"""
Shared building-block schemas used by both Model and Service domains.
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import BaseSchema
from app.schemas.enums import LicenseEnum, TaskTypeEnum


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


class ModelProcessingType(BaseSchema):
    type: str


class InferenceSchemaSpec(BaseModel):
    """The (request, response) schema embedded in a model's inference_endpoint."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="allow")

    modelProcessingType: Optional[ModelProcessingType] = None
    model_name: Optional[str] = None
    request: Dict[str, Any] = {}
    response: Dict[str, Any] = {}


class InferenceEndPoint(BaseModel):
    """Model-level inference endpoint metadata (the model card).

    The ``schema`` JSON key is aliased to ``endpoint_schema`` in Python to
    avoid shadowing Pydantic v2's ``BaseModel.schema`` class method.
    Serialization back to JSON still uses the ``schema`` key via the alias.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="allow")

    endpoint_schema: Optional[InferenceSchemaSpec] = Field(None, alias="schema")
    call_back_url: Optional[str] = None
    adapter_config: Optional[Dict[str, Any]] = None


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
