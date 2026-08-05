"""
Shared building-block schemas used by both Model and Service domains.
"""

import re
from typing import Any, Generic, List, Optional, TypeVar
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

    type: TaskTypeEnum = Field(
        ...,
        description="Required. The category of task this model performs.",
    )

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


# ── Submitter / team ──


class OAuthId(BaseSchema):
    """OAuth identity of a contributor/submitter (ULCA ``OAuthIdentity``)."""

    identifier: Optional[str] = Field(None, description="Optional. System identifier for the contributor.")
    oauthId: Optional[str] = Field(None, description="Optional. Social/OAuth identifier returned after auth.")
    provider: Optional[OAuthProviderEnum] = Field(None, description="Optional. Auth provider used.")


class TeamMember(BaseModel):
    """A contributor on the submitter's team (ULCA ``Contributor``)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="ignore")

    name: str = Field(..., min_length=5, max_length=50, description="Required. 5-50 characters.")
    aboutMe: Optional[str] = Field(None, description="Optional. Short bio for this contributor.")
    oauthId: Optional[OAuthId] = Field(None, description="Optional.")


class Submitter(BaseSchema):
    """The model provider — who submitted this model (ULCA ``Submitter``)."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Required. Name of the model provider/organization. 3-50 characters.",
    )
    oauthId: Optional[OAuthId] = Field(None, description="Optional.")
    aboutMe: Optional[str] = Field(None, description="Optional. Short description of the submitter.")
    team: List[TeamMember] = Field(
        default_factory=list,
        description="Optional, default: []. Contributors on the submitting team.",
    )


# ── Language ──


class LanguagePair(BaseSchema):
    """A language, or source/target language pair, a model supports (ULCA
    ``LanguagePair``). Leave ``targetLanguage`` unset to indicate a single
    language rather than a pair (e.g. ASR, TTS, OCR). Scope note: only
    ULCA's Indic + English language list is accepted — see
    SupportedLanguagesEnum."""

    sourceLanguage: SupportedLanguagesEnum = Field(
        ..., description="Required. ISO-639-1/2 Indic language code, or 'en'."
    )
    sourceLanguageName: Optional[str] = Field(None, description="Optional. Human-readable name, e.g. 'Hindi'.")
    sourceScriptCode: Optional[SupportedScriptsEnum] = Field(
        None, description="Optional. ISO-15924 script code, e.g. 'Deva'."
    )
    targetLanguage: Optional[SupportedLanguagesEnum] = Field(
        None, description="Optional. Omit/null for a single-language entry rather than a pair."
    )
    targetLanguageName: Optional[str] = Field(None, description="Optional. Human-readable name.")
    targetScriptCode: Optional[SupportedScriptsEnum] = Field(None, description="Optional. ISO-15924 script code.")


# ── Training dataset ──


class TrainingDataset(BaseSchema):
    """Training dataset metadata used to train the model (ULCA ``TrainingDataset``)."""

    description: str = Field(..., description="Required. Explain the dataset used to train this model.")
    datasetId: Optional[str] = Field(
        None,
        description="Optional. Identifier of a dataset already exported from the ULCA system, if applicable.",
    )


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
