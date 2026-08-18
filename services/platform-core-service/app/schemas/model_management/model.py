"""
Pydantic request/response schemas for the Model domain.

API contract preserves the existing camelCase keys used by the deprecated
model-management-service so that consumers (gateway, frontends) do not break
during migration.
"""

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from app.schemas.base import BaseSchema
from app.schemas.common import (
    AsyncApiDetails,
    Benchmark,
    InferenceApiKey,
    LanguagePair,
    MessageMeta,
    SuccessResponse,
    SuccessResponseWithMeta,
    Submitter,
    TaskSpec,
    TaskSpecLenient,
    TrainingDataset,
    validate_entity_name,
    validate_license,
)
from app.schemas.enums.model_management import DomainEnum, TaskTypeEnum, VersionStatusEnum


# ── Create / Update ──


_MODEL_CREATE_EXAMPLE = {
    "name": "ai4bharat/indictrans2-en-hi",
    "version": "v1",
    "description": (
        "Neural machine translation model for English to Hindi, fine-tuned "
        "on parliamentary and news domain text."
    ),
    "refUrl": "https://github.com/AI4Bharat/IndicTrans2",
    "task": {"type": "nmt"},
    "languages": [
        {
            "sourceLanguage": "en",
            "sourceLanguageName": "English",
            "sourceScriptCode": "Latn",
            "targetLanguage": "hi",
            "targetLanguageName": "Hindi",
            "targetScriptCode": "Deva",
        }
    ],
    "isLangDetectionEnabled": False,
    "isMultilingual": False,
    "license": "mit",
    "licenseUrl": "https://opensource.org/licenses/MIT",
    "domain": ["general", "news"],
    "submitter": {
        "name": "AI4Bharat",
        "aboutMe": "Open-source Indic NLP initiative at IIT Madras.",
        "team": [{"name": "AI4Bharat Research Team"}],
    },
    "adapterConfig": {
        "version": "1.0",
        "model_version": "1",
        "inputs": [
            {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
            {"tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.source_language"},
            {"tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.target_language"},
        ],
        "outputs": [
            {"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target"},
        ],
    },
    "schema": {
        "taskType": "translation",
        "request": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
        "response": {"output": [{"target": "string"}]},
        "model_name": "indictrans2-en-hi",
    },
    "callbackUrl": "https://inference.example.com/v2/models/indictrans2-en-hi/infer",
    "inferenceApiKey": {"name": "Authorization", "value": "<your-api-key>"},
    "isSyncApi": True,
    "asyncApiDetails": {
        "pollingUrl": "https://inference.example.com/v2/poll",
        "pollInterval": 1000,
    },
    "benchmarks": [],
    "trainingDataset": {
        "description": (
            "Parallel English-Hindi corpus sourced from parliamentary "
            "proceedings and news articles."
        ),
        "datasetId": "indictrans2-en-hi-corpus-v1",
    },
    "classInstance": None,
}

_PAIR_TASK_TYPES = {TaskTypeEnum.nmt, TaskTypeEnum.transliteration, TaskTypeEnum.llm}


def _require_full_pair(task_type: Optional[Any], languages: Optional[List[LanguagePair]]) -> None:
    """Enforce complete language-pair fields for translation/transliteration tasks."""
    if task_type not in _PAIR_TASK_TYPES or not languages:
        return
    for i, lp in enumerate(languages):
        errors = []
        if not lp.sourceLanguageName or not lp.sourceLanguageName.strip():
            errors.append("sourceLanguageName")
        if lp.sourceScriptCode is None:
            errors.append("sourceScriptCode")
        if lp.targetLanguage is None:
            errors.append("targetLanguage")
        if not lp.targetLanguageName or not lp.targetLanguageName.strip():
            errors.append("targetLanguageName")
        if lp.targetScriptCode is None:
            errors.append("targetScriptCode")
        if errors:
            raise ValueError(
                f"languages[{i}]: {', '.join(errors)} are required for "
                f"task type '{task_type}'"
            )


class ModelCreateRequest(BaseSchema):
    """Request body for POST /models.

    Field-level notes below call out which fields are optional and which
    have defaults; everything else listed is required. See the "Example
    Value" tab for a full worked ULCA-conformant payload.
    """

    model_config = ConfigDict(populate_by_name=True, json_schema_extra={"example": _MODEL_CREATE_EXAMPLE})

    version: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Required. Version identifier for this model, e.g. 'v1'. 1-20 characters.",
    )
    versionStatus: Optional[VersionStatusEnum] = Field(
        VersionStatusEnum.ACTIVE,
        description=(
            "Optional, default: 'ACTIVE'. Models cannot be created directly "
            "as 'DEPRECATED' — that's a lifecycle transition applied after "
            "creation via PATCH."
        ),
    )
    submittedOn: Optional[int] = Field(
        None, description="Ignored on input — auto-generated server-side (Unix epoch seconds)."
    )
    updatedOn: Optional[int] = Field(
        None, description="Ignored on input — auto-generated server-side (Unix epoch seconds)."
    )
    name: str = Field(
        ...,
        min_length=5,
        max_length=100,
        description=(
            "Required. Model name shown to users. 5-100 characters; "
            "alphanumeric, hyphens, and slashes only (no spaces), "
            "e.g. 'ai4bharat/indictrans2-en-hi'."
        ),
    )
    description: str = Field(
        ...,
        min_length=25,
        max_length=1000,
        description="Required. Brief description of the model and its goal. 25-1000 characters.",
    )
    refUrl: Optional[str] = Field(
        None,
        min_length=5,
        max_length=200,
        description="Optional. GitHub link or URL with more info about the model. 5-200 characters if provided.",
    )
    task: TaskSpec = Field(..., description="Required. The task category this model performs.")
    languages: Optional[List[LanguagePair]] = Field(
        None,
        description=(
            "Optional. Languages (or source/target pairs) this model "
            "supports — see LanguagePair. Restricted to ULCA's Indic + "
            "English language list."
        ),
    )
    isLangDetectionEnabled: StrictBool = Field(
        default=False,
        description="Optional, default: false. True if this model can auto-detect the input language on its own.",
    )
    isMultilingual: StrictBool = Field(
        default=False,
        description="Optional, default: false. True if this single model handles multiple languages itself.",
    )
    license: str = Field(
        ...,
        description=(
            "Required. License under this model is published — one of "
            "ULCA's License values (e.g. 'mit', 'cc-by-4.0', 'gpl-3.0', "
            "'custom-license'). Case-insensitive."
        ),
    )
    licenseUrl: Optional[str] = Field(
        None, max_length=500, description="Optional. URL of the custom license text. Max 500 characters."
    )
    domain: List[DomainEnum] = Field(
        ...,
        description="Required, at least one. Business area(s) this model is relevant to (ULCA Domain enum).",
    )
    adapterConfig: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional. Platform-specific Triton I/O tensor mapping. When provided, must include 'inputs' and 'outputs'.",
    )
    endpoint_schema: Optional[Dict[str, Any]] = Field(
        None,
        alias="schema",
        description=(
            "Optional. Task-specific inference request/response contract "
            "(e.g. {\"taskType\": \"translation\", \"model_name\": \"...\"}). "
            "The nested ``model_name`` key is used by the inference service "
            "to construct the Triton URL."
        ),
    )
    callbackUrl: Optional[str] = Field(
        None,
        description="Optional. The live URL inference requests are POSTed to.",
    )
    inferenceApiKey: Optional[InferenceApiKey] = Field(
        None,
        description="Optional. Auth header expected by callbackUrl.",
    )
    isSyncApi: Optional[StrictBool] = Field(
        None,
        description="Optional. True if inference is synchronous; False means async — asyncApiDetails should also be provided.",
    )
    asyncApiDetails: Optional[AsyncApiDetails] = Field(
        None,
        description="Optional. Required when isSyncApi is False. Provides pollingUrl and pollInterval for async validation.",
    )
    benchmarks: List[Benchmark] = Field(
        default_factory=list, description="Optional, default: []. Performance benchmark entries for this model."
    )
    submitter: Submitter = Field(
        ..., description="Required. The model provider — who submitted this model to the registry."
    )
    trainingDataset: TrainingDataset = Field(
        ...,
        description="Required. Metadata describing the dataset used to train this model (at minimum a description).",
    )
    classInstance: Optional[str] = Field(None, description="Optional. Internal platform classification tag.")

    @model_validator(mode="before")
    @classmethod
    def _reject_inference_end_point(cls, values: Any) -> Any:
        if isinstance(values, dict) and "inferenceEndPoint" in values:
            raise ValueError(
                "'inferenceEndPoint' was removed. "
                "Use top-level fields instead: 'adapterConfig', 'schema', "
                "'callbackUrl', 'inferenceApiKey', 'isSyncApi', 'asyncApiDetails'."
            )
        return values

    @field_validator("endpoint_schema", mode="after")
    @classmethod
    def _require_model_name_in_schema(cls, v: Any) -> Any:
        if v is not None and "model_name" not in v:
            raise ValueError(
                "schema must include 'model_name' — the Triton model identifier "
                "used to construct the inference URL (e.g. 'indictrans2-en-hi')"
            )
        return v

    @field_validator("adapterConfig", mode="after")
    @classmethod
    def _require_adapter_config_fields(cls, v: Any) -> Any:
        if v is not None:
            missing = [f for f in ("inputs", "outputs") if f not in v]
            if missing:
                raise ValueError(
                    f"adapterConfig must include {missing} — "
                    "the Triton tensor mapping used to build inference requests"
                )
        return v

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

    @model_validator(mode="after")
    def _validate_pair_languages(self) -> "ModelCreateRequest":
        _require_full_pair(self.task.type if self.task else None, self.languages)
        return self


_MODEL_UPDATE_EXAMPLE = {
    "modelId": "65bca5f3baae454fdb411646432ed1a2",  # sha256("ai4bharat/indictrans2-en-hi:v1")[:32] — matches the create example above
    "version": "v1",
    "description": (
        "Updated: neural machine translation model for English to Hindi, "
        "retrained on an expanded parliamentary and news corpus."
    ),
    "license": "cc-by-4.0",
    "licenseUrl": "https://creativecommons.org/licenses/by/4.0/",
    "isMultilingual": True,
    # Partial updates: only the keys sent are merged — omit any field to leave it unchanged.
    "adapterConfig": {"version": "2"},
    "callbackUrl": "https://inference.example.com/v2/models/indictrans2-en-hi/infer",
    "inferenceApiKey": {"name": "Authorization", "value": "<your-api-key>"},
    "isSyncApi": False,
    "asyncApiDetails": {
        "pollingUrl": "https://inference.example.com/v2/poll",
        "pollInterval": 1000,
    },
    "trainingDataset": {
        "description": (
            "Expanded parallel English-Hindi corpus, now including "
            "web-crawled news data."
        ),
        "datasetId": "indictrans2-en-hi-corpus-v2",
    },
}


class ModelUpdateRequest(BaseSchema):
    """Request body for PATCH /models.

    modelId + version identify the target and are the only fields required;
    every other field is optional — omit any field to leave it unchanged.
    See the "Example Value" tab for a realistic partial update.
    """

    model_config = ConfigDict(populate_by_name=True, json_schema_extra={"example": _MODEL_UPDATE_EXAMPLE})

    modelId: str = Field(..., description="Required. Identifies the model to update, together with version.")
    version: Optional[str] = Field(
        None, min_length=1, max_length=20, description="Required. The specific version to update."
    )
    versionStatus: Optional[VersionStatusEnum] = Field(
        None, description="Optional — omit to leave unchanged. 'ACTIVE' or 'DEPRECATED'."
    )
    description: Optional[str] = Field(
        None, min_length=25, max_length=1000, description="Optional — omit to leave unchanged. 25-1000 characters."
    )
    refUrl: Optional[str] = Field(
        None, min_length=5, max_length=200, description="Optional — omit to leave unchanged."
    )
    task: Optional[TaskSpec] = Field(None, description="Optional — omit to leave unchanged.")
    languages: Optional[List[LanguagePair]] = Field(None, description="Optional — omit to leave unchanged.")
    isLangDetectionEnabled: Optional[StrictBool] = Field(None, description="Optional — omit to leave unchanged.")
    isMultilingual: Optional[StrictBool] = Field(None, description="Optional — omit to leave unchanged.")
    license: Optional[str] = Field(
        None, description="Optional — omit to leave unchanged. Must be a valid ULCA License value if provided."
    )
    licenseUrl: Optional[str] = Field(
        None, max_length=500, description="Optional — omit to leave unchanged. Max 500 characters."
    )
    domain: Optional[List[DomainEnum]] = Field(None, description="Optional — omit to leave unchanged.")
    adapterConfig: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional — omit to leave unchanged. Sent keys are deep-merged into the stored adapterConfig.",
    )
    endpoint_schema: Optional[Dict[str, Any]] = Field(
        None,
        alias="schema",
        description="Optional — omit to leave unchanged. Replaces the stored schema entirely when provided.",
    )
    callbackUrl: Optional[str] = Field(None, description="Optional — omit to leave unchanged.")
    inferenceApiKey: Optional[InferenceApiKey] = Field(None, description="Optional — omit to leave unchanged.")
    isSyncApi: Optional[StrictBool] = Field(None, description="Optional — omit to leave unchanged.")
    asyncApiDetails: Optional[AsyncApiDetails] = Field(None, description="Optional — omit to leave unchanged.")
    benchmarks: Optional[List[Benchmark]] = Field(None, description="Optional — omit to leave unchanged.")
    submitter: Optional[Submitter] = Field(None, description="Optional — omit to leave unchanged.")
    trainingDataset: Optional[TrainingDataset] = Field(None, description="Optional — omit to leave unchanged.")
    classInstance: Optional[str] = Field(None, description="Optional — omit to leave unchanged.")

    @model_validator(mode="before")
    @classmethod
    def _reject_inference_end_point(cls, values: Any) -> Any:
        if isinstance(values, dict) and "inferenceEndPoint" in values:
            raise ValueError(
                "'inferenceEndPoint' was removed. "
                "Use top-level fields instead: 'adapterConfig', 'schema', "
                "'callbackUrl', 'inferenceApiKey', 'isSyncApi', 'asyncApiDetails'."
            )
        return values

    @field_validator("endpoint_schema", mode="after")
    @classmethod
    def _require_model_name_in_schema(cls, v: Any) -> Any:
        if v is not None and "model_name" not in v:
            raise ValueError(
                "schema must include 'model_name' — the Triton model identifier "
                "used to construct the inference URL (e.g. 'indictrans2-en-hi')"
            )
        return v

    @field_validator("license", mode="before")
    @classmethod
    def _validate_license(cls, v: Any) -> Any:
        return validate_license(v)

    @model_validator(mode="after")
    def _validate_pair_languages(self) -> "ModelUpdateRequest":
        _require_full_pair(self.task.type if self.task else None, self.languages)
        return self


# ── View / Response ──


class ModelViewRequest(BaseSchema):
    """Optional body for POST /models/{model_id} — pinning a specific version."""

    version: Optional[str] = None


class InferenceEndpointSchema(BaseSchema):
    """Task-specific inference request/response contract (the ``schema`` field).

    ``model_name`` (the Triton model identifier used to construct the
    inference URL, e.g. 'indictrans2-en-hi') is the only key the write-side
    validator requires — everything else genuinely varies per task type, so
    it's left optional here too (defensively — this is a response model, it
    must not fail to read back a row written before that validator existed)
    and any other key is preserved as-is.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    model_name: Optional[str] = None
    taskType: Optional[str] = Field(None, description="e.g. 'translation'.")


class AdapterConfigSchema(BaseSchema):
    """Platform-specific Triton I/O tensor mapping (the ``adapterConfig`` field).

    ``inputs``/``outputs`` are the two keys the create-time validator
    requires present (their internal tensor-descriptor shape isn't enforced
    beyond that, so they stay loosely typed). ``model_name`` is the
    authoritative real model identifier used for LLM (OpenAI-compatible)
    deployments (see ``utils/probe_payloads.py``, ``utils/endpoint_validator.py``).
    All fields are optional here — defensively, since this is a response
    model reading back whatever was actually persisted. Any other key is
    preserved as-is.
    """

    model_config = ConfigDict(extra="allow")

    inputs: Optional[Any] = Field(None, description="Triton input tensor mapping.")
    outputs: Optional[Any] = Field(None, description="Triton output tensor mapping.")
    model_name: Optional[str] = Field(
        None, description="Authoritative real model identifier — used for LLM task-type deployments."
    )


class ModelResponse(BaseSchema):
    """Single-model response shape (preserves model-management camelCase)."""

    model_config = ConfigDict(populate_by_name=True)

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
    adapterConfig: Optional[AdapterConfigSchema] = None
    endpoint_schema: Optional[InferenceEndpointSchema] = Field(None, alias="schema")
    callbackUrl: Optional[str] = None
    inferenceApiKey: Optional[InferenceApiKey] = None
    isSyncApi: Optional[bool] = None
    asyncApiDetails: Optional[AsyncApiDetails] = None
    source: Optional[str] = None  # alias for refUrl
    task: TaskSpecLenient
    trainingDataset: Optional[TrainingDataset] = None
    classInstance: Optional[str] = None
    createdAt: Optional[str] = None
    createdBy: Optional[str] = None
    updatedBy: Optional[str] = None


class ModelListItem(ModelResponse):
    """One row in a list response — same shape as ModelResponse for now."""


class ModelListResponse(BaseSchema):
    """Wrapped list response so we can attach metadata (count, filters)."""

    items: List[ModelListItem]
    total: int


# ── Route-specific ``data`` / ``meta`` shapes ──


class CreateModelData(BaseSchema):
    """``data`` shape for ``POST /models``."""

    modelId: str
    name: str
    version: str


class UpdateModelData(BaseSchema):
    """``data`` shape for ``PATCH /models``."""

    modelId: str
    version: str


class DeleteModelData(BaseSchema):
    """``data`` shape for ``DELETE /models/{model_id}``."""

    modelId: str


class ModelListMeta(BaseSchema):
    """``meta`` shape for ``GET /models`` — pagination info alongside the page of items."""

    total: int
    offset: int
    limit: int


# ── Route response envelopes — ``{"success": true, "data": ..., "meta": ...}`` ──


class ListModelsResponse(SuccessResponseWithMeta):
    """GET /models"""

    data: List[ModelResponse]
    meta: ModelListMeta


class GetModelResponse(SuccessResponse):
    """GET /models/{model_id}"""

    data: ModelResponse


class CreateModelResponse(SuccessResponseWithMeta):
    """POST /models"""

    data: CreateModelData
    meta: MessageMeta


class UpdateModelResponse(SuccessResponseWithMeta):
    """PATCH /models"""

    data: UpdateModelData
    meta: MessageMeta


class DeleteModelResponse(SuccessResponseWithMeta):
    """DELETE /models/{model_id}"""

    data: DeleteModelData
    meta: MessageMeta
