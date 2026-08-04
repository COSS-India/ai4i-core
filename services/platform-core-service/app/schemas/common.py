"""
Shared building-block schemas used by both Model and Service domains.
"""

import re
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


# ── Inference endpoint schema (model definition, not the live endpoint URL) ──


class InferenceApiKey(BaseModel):
    """Auth header expected by the model's callback URL (ULCA ``inferenceApiKey``)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="ignore")

    name: str = Field(
        default="Authorization",
        description="Optional. Header name the callback URL expects the API key under. Defaults to 'Authorization' if omitted.",
    )
    value: str = Field(
        ...,
        description="Required (if inferenceApiKey is provided at all). The API key/token value sent in that header. Masked as '[REDACTED]' on every read (GET/list) — resend the real value on updates, never the redacted sentinel.",
    )


class AsyncApiDetails(BaseModel):
    """Polling details for async inference (ULCA ``AsyncApiDetails``).

    ``asyncApiSchema``/``asyncApiPollingSchema`` are task-specific request/
    response contracts validated by the inference service, so they stay a
    flexible passthrough here rather than a fully modeled discriminated union.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="ignore")

    pollingUrl: str = Field(..., description="Required. Endpoint to poll for async inference status.")
    pollInterval: int = Field(..., description="Required. Polling interval in milliseconds.")
    asyncApiSchema: Optional[Dict[str, Any]] = Field(
        None, description="Optional. Task-specific async request/response schema."
    )
    asyncApiPollingSchema: Optional[Dict[str, Any]] = Field(
        None, description="Optional. Task-specific polling response schema."
    )


class InferenceEndPoint(BaseModel):
    """Model-level inference endpoint metadata (ULCA ``InferenceAPIEndPoint``).

    The ``schema`` JSON key is aliased to ``endpoint_schema`` in Python to
    avoid shadowing Pydantic v2's ``BaseModel.schema`` class method. Its
    task-specific request/response contract is validated by the inference
    service, not the model registry, so it stays a flexible passthrough dict
    here rather than a fully modeled discriminated union.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="allow",
        json_schema_extra={
            "example": {
                "callbackUrl": "https://inference.example.com/v2/models/indictrans2-en-hi/infer",
                "inferenceApiKey": {"name": "Authorization", "value": "<your-api-key>"},
                "isMultilingualEnabled": False,
                "schema": {"taskType": "translation"},
                "isSyncApi": True,
            }
        },
    )

    callbackUrl: str = Field(
        ...,
        description="Required. The live URL this model's inference requests are POSTed to.",
    )
    inferenceApiKey: Optional[InferenceApiKey] = Field(
        None,
        description="Optional. Only needed if callbackUrl requires an API key/auth header to invoke.",
    )
    isMultilingualEnabled: bool = Field(
        default=False,
        description="Optional, default: false. True if this callbackUrl itself can handle multiple languages without extra config.",
    )
    endpoint_schema: Dict[str, Any] = Field(
        ...,
        alias="schema",
        description=(
            "Required. Task-specific inference request/response contract "
            "(e.g. {\"taskType\": \"translation\", ...}). Validated by the "
            "inference service at call time, not by the model registry — "
            "pass {} if you don't need to declare one up front."
        ),
    )
    isSyncApi: Optional[bool] = Field(
        None,
        description="Optional. True if inference is synchronous; false means the model is async and asyncApiDetails should be provided.",
    )
    asyncApiDetails: Optional[AsyncApiDetails] = Field(
        None, description="Optional. Required in practice only when isSyncApi is false."
    )
    adapter_config: Optional[Dict[str, Any]] = Field(
        None,
        alias="adapterConfig",
        description="Optional. Platform-specific Triton I/O tensor mapping — not part of the ULCA spec.",
    )


class InferenceEndPointPatch(BaseModel):
    """Partial-update variant of :class:`InferenceEndPoint` for PATCH /models.

    ``update_model`` deep-merges only the keys the caller actually sent into
    the existing stored endpoint (see ``ModelService.update_model``), so a
    PATCH that touches only e.g. ``adapterConfig`` or
    ``isMultilingualEnabled`` must not be forced to also resend
    ``callbackUrl``/``schema``. Those two stay required on the create-time
    :class:`InferenceEndPoint`; here every field is optional.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="allow")

    callbackUrl: Optional[str] = Field(None, description="Optional — omit to leave unchanged.")
    inferenceApiKey: Optional[InferenceApiKey] = Field(
        None,
        description=(
            "Optional — omit to leave unchanged. Never resend the "
            "'[REDACTED]' value returned by GET; that sentinel is stripped "
            "before merge and won't overwrite the stored secret, but "
            "sending the real value here does update it."
        ),
    )
    isMultilingualEnabled: Optional[bool] = Field(None, description="Optional — omit to leave unchanged.")
    endpoint_schema: Optional[Dict[str, Any]] = Field(
        None, alias="schema", description="Optional — omit to leave unchanged."
    )
    isSyncApi: Optional[bool] = Field(None, description="Optional — omit to leave unchanged.")
    asyncApiDetails: Optional[AsyncApiDetails] = Field(None, description="Optional — omit to leave unchanged.")
    adapter_config: Optional[Dict[str, Any]] = Field(
        None, alias="adapterConfig", description="Optional — omit to leave unchanged."
    )


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
    """A source/target language pair a model supports (ULCA ``LanguagePair``).
    Both source and target are required, along with their language name and
    script code. Scope note: only ULCA's Indic + English language list is
    accepted — see SupportedLanguagesEnum."""

    sourceLanguage: SupportedLanguagesEnum = Field(
        ..., description="Required. ISO-639-1/2 Indic language code, or 'en'."
    )
    sourceLanguageName: str = Field(..., description="Required. Human-readable name, e.g. 'Hindi'.")
    sourceScriptCode: SupportedScriptsEnum = Field(
        ..., description="Required. ISO-15924 script code, e.g. 'Deva'."
    )
    targetLanguage: SupportedLanguagesEnum = Field(
        ..., description="Required. Target language for this pair."
    )
    targetLanguageName: str = Field(..., description="Required. Human-readable name.")
    targetScriptCode: SupportedScriptsEnum = Field(..., description="Required. ISO-15924 script code.")

    @model_validator(mode="after")
    def _validate_language_pair(self) -> "LanguagePair":
        if not self.sourceLanguageName.strip():
            raise ValueError("sourceLanguageName must not be blank")
        if not self.targetLanguageName.strip():
            raise ValueError("targetLanguageName must not be blank")
        return self


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
