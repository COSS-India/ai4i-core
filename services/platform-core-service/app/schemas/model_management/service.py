"""
Pydantic request/response schemas for the Service domain.

ULCA alignment: `task` and `inferenceEndPoint` are ULCA's literal field
names on the `Service` schema (deployment-service-specs.yml); their values
conform to ULCA's `ModelTask` (reusing the `TaskSpec` class Model already
uses) and `InferenceAPIEndPoint` schemas respectively. The previous flat
fields (`taskType`, `endpoint`, `hardwareDescription`, `api_key`,
`serviceDescription`) are kept as deprecated aliases — accepted on input
and still returned on output — so existing callers keep working while new
integrations use the ULCA-conformant shape.
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.core.config import settings
from app.schemas.base import BaseSchema
from app.schemas.common import (
    AsyncApiDetails,
    BenchmarkEntry,
    InferenceApiKey,
    TaskSpec,
    validate_entity_name,
)
from app.schemas.enums.model_management import (
    AudioFormatEnum,
    InferenceServerTypeEnum,
    TaskTypeEnum,
    TextFormatEnum,
    resolve_task_type,
)
from app.schemas.model_management.model import ModelResponse


# ── Health sub-schema ──


class ServiceStatus(BaseSchema):
    status: Optional[str] = None
    lastUpdated: Optional[str] = None


# ── Create / Update ──


SERVICE_ID_RE = re.compile(r"^(?=.*[a-zA-Z0-9])[a-zA-Z0-9/_-]+$")
SERVICE_ID_MAX_LEN = 255
# ULCA's serviceId minLength — enforced on new creates only. NOT added to
# validate_service_id() below, which is also used to validate existing
# serviceIds on GET/DELETE lookups; tightening it there would break
# fetching/deleting any already-existing short-ID service.
SERVICE_ID_MIN_LEN_ON_CREATE = 5


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


def validate_expected_response_schema(
    v: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Shared by Create/Update: None is fine (falls back to the built-in
    per-task-type default — see app.utils.probe_payloads), but an explicitly
    supplied schema must be a non-empty object."""
    if v is not None and not v:
        raise ValueError(
            "expectedResponseSchema must be a non-empty object describing "
            "the expected response shape"
        )
    return v


_EXPECTED_RESPONSE_SCHEMA_DESCRIPTION = (
    "Optional. A sample of what a correct response from this endpoint "
    'looks like, e.g. {"output": [{"target": "..."}]}. The endpoint is '
    "probed with a task-type-appropriate sample request, and its actual "
    "response must structurally match this shape (same keys, same value "
    "types) or the service is rejected. When omitted, a built-in default "
    "shape for the model's task type is used instead (see "
    "app.utils.probe_payloads.get_expected_response_shape); task types with "
    "no known default simply skip this check. Supply this to override the "
    "default or to validate a custom/non-ULCA response contract. Distinct "
    "from `inferenceEndPoint.schema` — that's a declared per-task contract, "
    "this is a live smoke-test fixture."
)

_DESCRIPTION_MIN_LEN = 25
_DESCRIPTION_MAX_LEN = 1000


def _resolve_and_check_description(
    description: Optional[str], legacy_service_description: Optional[str]
) -> str:
    resolved = description if description is not None else legacy_service_description
    if resolved is None:
        raise ValueError(
            "description is required (25-1000 characters, ULCA alignment). "
            "`serviceDescription` is accepted as a deprecated alias."
        )
    if not (_DESCRIPTION_MIN_LEN <= len(resolved) <= _DESCRIPTION_MAX_LEN):
        raise ValueError(
            f"description must be {_DESCRIPTION_MIN_LEN}-{_DESCRIPTION_MAX_LEN} characters."
        )
    return resolved


# One representative worked example (ASR) — mirrors ModelCreateRequest's
# _MODEL_CREATE_EXAMPLE pattern. Deliberately shows only the new ULCA-shaped
# `task`/`inferenceEndPoint` fields, not the deprecated flat aliases, since
# those are documented per-field via each alias's own `description` instead.
_SERVICE_CREATE_EXAMPLE = {
    "serviceId": "ai4bharat/conformer-hi-asr-gpu",
    "name": "Hindi Conformer ASR",
    "description": (
        "Indic-Conformer ASR model deployed by AI4Bharat for Hindi, served "
        "on a dedicated GPU inference cluster."
    ),
    "modelId": "65bca5f3baae454fdb411646432ed1a2",
    "modelVersion": "v1",
    "task": {"type": "asr"},
    "inferenceEndPoint": {
        "callbackUrl": "https://inference.example.com/v2/models/conformer-hi-asr/infer",
        "inferenceApiKey": {"name": "Authorization", "value": "<your-api-key>"},
        "isMultilingualEnabled": False,
        "supportedInputFormats": {"audio": ["wav"]},
        "supportedOutputFormats": {"text": ["transcript"]},
        "schema": [
            {
                "taskType": "asr",
                "request": {
                    "audio": [{"audioContent": "<base64-encoded-audio>"}],
                    "config": {"language": {"sourceLanguage": "hi"}, "audioFormat": "wav"},
                },
                "response": {"output": [{"source": "नमस्ते"}]},
            }
        ],
        "isSyncApi": True,
        "providerName": "AI4Bharat",
        "infraDescription": "Auto-scalable deployment, using T4 GPUs",
        "inferenceModelId": "conformer-hi-asr-v1",
    },
    "inferenceServerType": "triton",
    "sslVerify": True,
    "costPerUnit": 0.01,
    "unitSize": 100,
    "tierIds": ["tier-standard"],
    "expectedResponseSchema": {"output": [{"source": "..."}]},
}


class ServiceCreateRequest(BaseSchema):
    """Request body for POST /services. See the "Example Value" tab for a
    full worked ULCA-conformant payload."""

    model_config = ConfigDict(populate_by_name=True, json_schema_extra={"example": _SERVICE_CREATE_EXAMPLE})

    serviceId: str
    name: str = Field(..., min_length=5, max_length=100)
    description: Optional[str] = Field(
        None,
        description=(
            "Required (ULCA). Brief description of the service. "
            f"{_DESCRIPTION_MIN_LEN}-{_DESCRIPTION_MAX_LEN} characters. "
            "`serviceDescription` is accepted as a deprecated alias."
        ),
    )
    serviceDescription: Optional[str] = Field(
        None, description="Deprecated — use `description`. Kept as an accepted alias."
    )
    hardwareDescription: Optional[str] = Field(
        None, description="Deprecated — use `inferenceEndPoint.infraDescription`."
    )
    modelId: str
    modelVersion: str
    task: Optional[TaskSpec] = Field(
        None, description="Required. The task category this service performs (ULCA ModelTask)."
    )
    taskType: Optional[str] = Field(
        None, description="Deprecated — use `task.type`. Kept as an accepted alias."
    )
    inferenceEndPoint: Optional[InferenceAPIEndPoint] = Field(
        None, description="Required (ULCA). Deployment endpoint config."
    )
    endpoint: Optional[str] = Field(
        None, description="Deprecated — use `inferenceEndPoint.callbackUrl`."
    )
    api_key: Optional[str] = Field(
        None,
        description=(
            "Deprecated — use `inferenceEndPoint.inferenceApiKey.value`. "
            "Kept as an accepted alias; defaults to the 'Authorization' "
            "header name when used."
        ),
    )
    inferenceServerType: InferenceServerTypeEnum = InferenceServerTypeEnum.triton
    sslVerify: bool = True
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    costPerUnit: float = Field(..., ge=0)
    unitSize: int
    tierIds: List[str] = Field(..., min_length=1)
    expectedResponseSchema: Optional[Dict[str, Any]] = Field(
        None, description=_EXPECTED_RESPONSE_SCHEMA_DESCRIPTION
    )

    @field_validator("taskType")
    @classmethod
    def _validate_task_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return resolve_task_type(v)

    @field_validator("expectedResponseSchema")
    @classmethod
    def _validate_expected_response_schema(
        cls, v: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        return validate_expected_response_schema(v)

    @field_validator("serviceId")
    @classmethod
    def _validate_service_id(cls, v: str) -> str:
        v = validate_service_id(v)
        if len(v) < SERVICE_ID_MIN_LEN_ON_CREATE:
            raise ValueError(
                f"serviceId must be at least {SERVICE_ID_MIN_LEN_ON_CREATE} "
                "characters (ULCA alignment). Only applies to new services "
                "— existing shorter IDs are unaffected."
            )
        return v

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

    @model_validator(mode="after")
    def _reconcile_ulca_fields(self) -> "ServiceCreateRequest":
        """Single reconciliation point: merges the deprecated flat aliases
        (`taskType`, `endpoint`, `hardwareDescription`, `api_key`,
        `serviceDescription`) into the ULCA-shaped `task`/`inferenceEndPoint`/
        `description` fields (or vice versa, whichever the caller used), and
        enforces ULCA's "required" rule on the merged result. Runs before
        `_require_billing_fields_on_substantive_edit`-equivalent checks don't
        apply here (create requires costPerUnit/unitSize/tierIds
        unconditionally already).

        Note: `inferenceEndPoint.schema` requiredness is NOT enforced here.
        Unlike callbackUrl/infraDescription (genuinely deployment-specific,
        nothing else could supply them), `schema` describes the underlying
        model's request/response contract — a property of the Model, not
        the deployment — so ServiceService.create_service derives it from
        the linked Model's own `schema` when the caller omits it, and only
        requires it manually as a fallback when the Model has none on file.
        """
        self.description = _resolve_and_check_description(
            self.description, self.serviceDescription
        )

        if self.task is not None:
            self.taskType = self.task.type
        elif self.taskType is not None:
            self.task = TaskSpec(type=self.taskType)
        else:
            raise ValueError(
                "task is required (`task.type`, or the deprecated `taskType` alias)."
            )

        ep = self.inferenceEndPoint or InferenceAPIEndPoint()
        callback_url = ep.callbackUrl or self.endpoint
        infra_description = ep.infraDescription or self.hardwareDescription
        inference_api_key = ep.inferenceApiKey
        if inference_api_key is None and self.api_key:
            inference_api_key = InferenceApiKey(value=self.api_key)

        missing = []
        if not callback_url:
            missing.append("inferenceEndPoint.callbackUrl (or deprecated `endpoint`)")
        if not infra_description:
            missing.append("inferenceEndPoint.infraDescription (or deprecated `hardwareDescription`)")
        if missing:
            raise ValueError(
                "inferenceEndPoint is required and missing: " + ", ".join(missing)
            )

        # Fail fast when the caller DID supply a schema — no point waiting
        # for the model lookup in the service layer to catch a mismatch we
        # can already see here. When schema is omitted (to be derived from
        # the model), there's nothing to check yet — ServiceService does
        # this same check again once the derived value is known.
        if ep.endpoint_schema and not schema_matches_task_type(self.taskType, ep.endpoint_schema):
            raise ValueError(
                f"inferenceEndPoint.schema must include at least one entry "
                f"whose taskType matches this service's task ('{self.taskType}'); "
                f"got: {[e.get('taskType') for e in ep.endpoint_schema]}"
            )

        self.inferenceEndPoint = _rebuild_inference_endpoint(
            ep,
            callback_url=callback_url,
            infra_description=infra_description,
            inference_api_key=inference_api_key,
        )
        # Keep the deprecated flat aliases in sync too, so downstream code
        # (service_service.py) that still reads them for the pre-existing
        # fields keeps working unmodified regardless of which channel the
        # caller actually used.
        self.endpoint = callback_url
        self.hardwareDescription = infra_description
        self.api_key = inference_api_key.value if inference_api_key else self.api_key
        return self


# Partial update — only the keys sent are merged, omit any field to leave it
# unchanged. taskType/costPerUnit/unitSize/tierIds are shown together since
# any substantive edit requires resending all four.
_SERVICE_UPDATE_EXAMPLE = {
    "serviceId": "ai4bharat/conformer-hi-asr-gpu",
    "description": (
        "Updated: Indic-Conformer ASR model for Hindi, now serving on "
        "upgraded A100 GPUs."
    ),
    "task": {"type": "asr"},
    "inferenceEndPoint": {
        "callbackUrl": "https://inference.example.com/v2/models/conformer-hi-asr/infer",
        "infraDescription": "Auto-scalable deployment, using A100 GPUs",
    },
    "costPerUnit": 0.008,
    "unitSize": 100,
    "tierIds": ["tier-standard"],
}


class ServiceUpdateRequest(BaseSchema):
    """Request body for PATCH /services. serviceId identifies the target.

    Note: name, modelId, modelVersion are NOT updatable. serviceId is not
    editable. See the "Example Value" tab for a realistic partial update.
    """

    model_config = ConfigDict(populate_by_name=True, json_schema_extra={"example": _SERVICE_UPDATE_EXAMPLE})

    # A request touching only these is the publish/unpublish toggle and is
    # exempt from _BILLING_FIELDS_REQUIRED_TOGETHER — requiring them
    # unconditionally, including on this toggle, would break that flow; see
    # _require_billing_fields_on_substantive_edit below.
    _PUBLISH_ONLY_FIELDS = {"serviceId", "isPublished", "isTryItDefault"}
    _BILLING_FIELDS_REQUIRED_TOGETHER = ("taskType", "costPerUnit", "unitSize", "tierIds")

    serviceId: str
    description: Optional[str] = Field(
        None,
        description=(
            "Use in place of the deprecated `serviceDescription`. Unlike "
            "on create, the 25-1000 char length rule is NOT enforced here "
            "— a pre-existing service with a shorter stored description "
            "must be able to resend it on an unrelated edit without 422ing."
        ),
    )
    serviceDescription: Optional[str] = Field(
        None, description="Deprecated — use `description`."
    )
    hardwareDescription: Optional[str] = Field(
        None, description="Deprecated — use `inferenceEndPoint.infraDescription`."
    )
    task: Optional[TaskSpec] = Field(
        None, description="Use in place of the deprecated `taskType`."
    )
    taskType: Optional[str] = None
    inferenceEndPoint: Optional[InferenceAPIEndPoint] = Field(
        None, description="Use in place of the deprecated `endpoint`/`hardwareDescription`/`api_key`."
    )
    endpoint: Optional[str] = Field(
        None, description="Deprecated — use `inferenceEndPoint.callbackUrl`."
    )
    api_key: Optional[str] = Field(
        None, description="Deprecated — use `inferenceEndPoint.inferenceApiKey.value`."
    )
    inferenceServerType: Optional[InferenceServerTypeEnum] = None
    sslVerify: Optional[bool] = None
    healthStatus: Optional[str] = None
    benchmarks: Optional[Dict[str, List[BenchmarkEntry]]] = None
    isPublished: Optional[bool] = None
    isTryItDefault: Optional[bool] = None
    costPerUnit: Optional[float] = Field(None, ge=0)
    unitSize: Optional[int] = None
    tierIds: Optional[List[str]] = None
    expectedResponseSchema: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            _EXPECTED_RESPONSE_SCHEMA_DESCRIPTION
            + " Supplying this on its own (without an `endpoint` change) "
            "still re-validates it against the current live endpoint before "
            "it's stored, so a schema is never persisted without having been "
            "checked against a real response. Omitting it on an `endpoint` "
            "change reuses the schema on file (or the task-type default)."
        ),
    )

    @field_validator("taskType")
    @classmethod
    def _validate_task_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return resolve_task_type(v)

    @field_validator("expectedResponseSchema")
    @classmethod
    def _validate_expected_response_schema(
        cls, v: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        return validate_expected_response_schema(v)

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
    def _reconcile_ulca_fields(self) -> "ServiceUpdateRequest":
        """Same merge as ServiceCreateRequest, but nothing is required here
        — this is a partial update, so any/all of these may be legitimately
        absent.

        The 25-1000 char length rule is deliberately NOT re-enforced here —
        same scoping as SERVICE_ID_MIN_LEN_ON_CREATE, create only. The
        admin edit form resends the stored description on every
        update (frontend/simple-ui/src/hooks/useServicesManagement.ts),
        so a service created before this rule existed, with a description
        under 25 chars, would otherwise 422 on its first unrelated edit
        (e.g. just changing the endpoint) after this ships.
        """
        if self.description is None and self.serviceDescription is not None:
            self.description = self.serviceDescription

        if self.task is not None:
            self.taskType = self.task.type
        elif self.taskType is not None:
            self.task = TaskSpec(type=self.taskType)

        if self.inferenceEndPoint is not None or self.endpoint or self.hardwareDescription or self.api_key:
            ep = self.inferenceEndPoint or InferenceAPIEndPoint()
            callback_url = ep.callbackUrl or self.endpoint
            infra_description = ep.infraDescription or self.hardwareDescription
            inference_api_key = ep.inferenceApiKey
            if inference_api_key is None and self.api_key:
                inference_api_key = InferenceApiKey(value=self.api_key)
            self.inferenceEndPoint = _rebuild_inference_endpoint(
                ep,
                callback_url=callback_url,
                infra_description=infra_description,
                inference_api_key=inference_api_key,
            )
            # Bug fix (found via live testing, not just mocks): only backfill
            # the deprecated flat aliases when there's an actual new value to
            # propagate. `inferenceEndPoint` being touched at all (e.g. just
            # `providerName`, with no callbackUrl/infraDescription supplied
            # via either channel) must NOT clobber `self.endpoint`/
            # `self.hardwareDescription` to None — `endpoint` is a NOT NULL
            # column (crashes the update with a 500) and `hardwareDescription`
            # is nullable (would silently null out an existing value instead).
            if callback_url is not None:
                self.endpoint = callback_url
            if infra_description is not None:
                self.hardwareDescription = infra_description
            if inference_api_key is not None:
                self.api_key = inference_api_key.value

        # Cross-check only when BOTH the task and the schema are part of
        # THIS update — if only one side is being changed, this schema
        # (Pydantic layer, no DB access) can't see what the other side's
        # current stored value is; ServiceService.update_service does that
        # comparison against the existing row.
        if (
            self.taskType is not None
            and self.inferenceEndPoint is not None
            and self.inferenceEndPoint.endpoint_schema is not None
            and not schema_matches_task_type(self.taskType, self.inferenceEndPoint.endpoint_schema)
        ):
            raise ValueError(
                f"inferenceEndPoint.schema must include at least one entry "
                f"whose taskType matches this service's task ('{self.taskType}'); "
                f"got: {[e.get('taskType') for e in self.inferenceEndPoint.endpoint_schema]}"
            )
        return self

    @model_validator(mode="after")
    def _require_billing_fields_on_substantive_edit(self) -> "ServiceUpdateRequest":
        """taskType/costPerUnit/unitSize/tierIds must be supplied together on
        any edit beyond the publish/unpublish toggle. `_reconcile_ulca_fields`
        above already backfilled `taskType` from `task` when only the latter
        was supplied, so checking the `taskType` attribute here still covers
        both input channels.

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


class ServiceEndpointUpdateItem(BaseSchema):
    """A single {serviceId, endpoint} pair, used by the bulk endpoint-update
    request below."""

    serviceId: str
    endpoint: str


class ServiceBulkEndpointUpdateRequest(BaseSchema):
    """Request body for PATCH /services when updating multiple services'
    endpoints in a single call: {"services": [{"serviceId", "endpoint"}, ...]}.

    Distinguished from ServiceUpdateRequest by the top-level "services" key,
    so both shapes can be accepted on the same route without ambiguity.

    Bypasses ServiceUpdateRequest's billing-fields-required-together rule by
    design: unlike that request, this shape can only ever touch `endpoint`,
    so there is no substantive-edit case to guard against here.
    """

    services: List[ServiceEndpointUpdateItem] = Field(
        ..., min_length=1, max_length=settings.bulk_endpoint_update_max_items
    )


# ── Response ──


class ServiceResponse(BaseSchema):
    """Single service response (lightweight — no embedded model)."""

    serviceId: str
    name: str
    description: Optional[str] = None
    serviceDescription: Optional[str] = Field(
        None, description="Deprecated — use `description`."
    )
    hardwareDescription: Optional[str] = Field(
        None, description="Deprecated — use `inferenceEndPoint.infraDescription`."
    )
    modelId: str
    modelVersion: str
    task: Optional[Dict[str, Any]] = None
    taskType: Optional[str] = Field(
        None, description="Deprecated — use `task.type`."
    )
    inferenceEndPoint: Optional[Dict[str, Any]] = None
    endpoint: Optional[str] = Field(
        None, description="Deprecated — use `inferenceEndPoint.callbackUrl`."
    )
    inferenceServerType: str = InferenceServerTypeEnum.triton.value
    sslVerify: bool = True
    api_key: Optional[str] = Field(
        None,
        description="Deprecated, masked — use `inferenceEndPoint.inferenceApiKey` (also masked).",
    )
    healthStatus: Optional[ServiceStatus] = None
    benchmarks: Optional[Dict[str, Any]] = None
    isPublished: bool = False
    isTryItDefault: bool = False
    publishedAt: Optional[str] = None
    unpublishedAt: Optional[str] = None
    costPerUnit: Optional[float] = None
    unitSize: Optional[int] = None
    unitRate: Optional[float] = None
    tierIds: Optional[List[str]] = None
    tierNames: Optional[List[str]] = None
    expectedResponseSchema: Optional[Dict[str, Any]] = None
    createdBy: Optional[str] = None
    updatedBy: Optional[str] = None


class ServiceListItem(ServiceResponse):
    """List response item — augmented with the inline model snippet."""

    languages: List[Dict[str, Any]] = Field(default_factory=list)
    versionStatus: Optional[str] = None


class ServiceListResponse(BaseSchema):
    """Wrapped list with count and filter context."""

    items: List[ServiceListItem]
    total: int


class ServiceDetailResponse(ServiceResponse):
    """Full service view — includes embedded model card."""

    model: Optional[ModelResponse] = None
