"""
Pydantic request/response schemas for the Model domain.

API contract preserves the existing camelCase keys used by the deprecated
model-management-service so that consumers (gateway, frontends) do not break
during migration.
"""

from typing import Any, List, Optional

from pydantic import ConfigDict, Field, field_validator, model_validator

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
    "inferenceEndPoint": {
        "callbackUrl": "https://inference.example.com/v2/models/indictrans2-en-hi/infer",
        "modelName": "indictrans2-en-hi",
        "inferenceApiKey": {"name": "Authorization", "value": "<your-api-key>"},
        "isMultilingualEnabled": False,
        "isSyncApi": True,
        "schema": {
            "taskType": "translation",
            "request": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
            "response": {"output": [{"target": "string"}]},
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

    model_config = ConfigDict(json_schema_extra={"example": _MODEL_CREATE_EXAMPLE})

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
    isLangDetectionEnabled: bool = Field(
        default=False,
        description="Optional, default: false. True if this model can auto-detect the input language on its own.",
    )
    isMultilingual: bool = Field(
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
    inferenceEndPoint: InferenceEndPoint = Field(
        ...,
        description=(
            "Required. The model's inference endpoint metadata (the model "
            "card) — callbackUrl and schema are themselves required; see "
            "InferenceEndPoint."
        ),
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
    # Partial inferenceEndPoint update: only the keys below are merged into
    # the stored endpoint — callbackUrl/schema don't need to be resent.
    "inferenceEndPoint": {
        "isMultilingualEnabled": True,
        "adapterConfig": {"version": "2"},
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
    See the "Example Value" tab for a realistic partial update, including
    the inferenceEndPoint partial-merge pattern.
    """

    model_config = ConfigDict(json_schema_extra={"example": _MODEL_UPDATE_EXAMPLE})

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
    isLangDetectionEnabled: Optional[bool] = Field(None, description="Optional — omit to leave unchanged.")
    isMultilingual: Optional[bool] = Field(None, description="Optional — omit to leave unchanged.")
    license: Optional[str] = Field(
        None, description="Optional — omit to leave unchanged. Must be a valid ULCA License value if provided."
    )
    licenseUrl: Optional[str] = Field(
        None, max_length=500, description="Optional — omit to leave unchanged. Max 500 characters."
    )
    domain: Optional[List[DomainEnum]] = Field(None, description="Optional — omit to leave unchanged.")
    inferenceEndPoint: Optional[InferenceEndPointPatch] = Field(
        None,
        description=(
            "Optional — omit to leave unchanged. Partial update: only the "
            "keys you send are merged into the stored endpoint, so you "
            "don't need to resend callbackUrl/schema to change e.g. just "
            "adapterConfig."
        ),
    )
    benchmarks: Optional[List[Benchmark]] = Field(None, description="Optional — omit to leave unchanged.")
    submitter: Optional[Submitter] = Field(None, description="Optional — omit to leave unchanged.")
    trainingDataset: Optional[TrainingDataset] = Field(None, description="Optional — omit to leave unchanged.")
    classInstance: Optional[str] = Field(None, description="Optional — omit to leave unchanged.")

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
