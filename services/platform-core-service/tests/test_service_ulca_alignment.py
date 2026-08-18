"""Unit tests: Service schema ULCA alignment.

Covers:
- `task`/`inferenceEndPoint` as real nested ULCA-shaped objects, accepted
  alongside the deprecated flat aliases (`taskType`/`endpoint`/
  `hardwareDescription`/`api_key`/`serviceDescription`).
- `description` required on create (25-1000 chars); `inferenceEndPoint`
  required on create (callbackUrl, infraDescription, schema).
- `serviceId` minimum length of 5 enforced on create only — not on the
  shared `validate_service_id` used for existing-ID lookups.
- `schema` (InferenceSchemaArray) shallow shape validation.
- New optional fields (isMultilingualEnabled, supportedInputFormats,
  supportedOutputFormats, providerName, inferenceModelId) reach the DB
  layer; a partial update that doesn't touch isMultilingualEnabled can't
  reset it.
- Response serialization: description/task/inferenceEndPoint always
  present; api_key/inferenceApiKey masked; inferenceEndPoint hidden from
  non-admin RBAC filtering (it carries infraDescription, the ULCA name for
  the already-admin-only hardwareDescription).
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import importlib

import pytest
from pydantic import ValidationError as PydanticValidationError

# ── Module-level stubs (mirrors test_service_create.py) ─────────────────────


def _stub_svc(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


_STUBBED_MODULE_NAMES = (
    "app.models",
    "app.models.model_management",
    "app.models.model_management.service",
    "app.models.model_management.model",
    "app.repositories",
    "app.repositories.model_management",
    "app.repositories.model_management.model_repository",
    "app.repositories.model_management.service_repository",
)
_newly_stubbed = [n for n in _STUBBED_MODULE_NAMES if n not in sys.modules]

_stub_svc("app.models")
_stub_svc("app.models.model_management")
_stub_svc("app.models.model_management.service", Service=MagicMock)
_stub_svc("app.models.model_management.model", Model=MagicMock)
_stub_svc("app.repositories")
_stub_svc("app.repositories.model_management")
_stub_svc("app.repositories.model_management.model_repository", ModelRepository=MagicMock)
_stub_svc("app.repositories.model_management.service_repository", ServiceRepository=MagicMock)

from app.core.exceptions import ValidationError  # noqa: E402
from app.schemas.model_management.service import (  # noqa: E402
    InferenceAPIEndPoint,
    ServiceCreateRequest,
    ServiceUpdateRequest,
    validate_service_id,
)
from app.schemas.common import TaskSpec  # noqa: E402

service_service_mod = importlib.import_module(
    "app.services.model-management.service_service"
)
ServiceService = service_service_mod.ServiceService

for _name in _newly_stubbed:
    sys.modules.pop(_name, None)


# ── Helpers ───────────────────────────────────────────────────────────────────

_LONG_DESCRIPTION = "A test service used for automated ULCA-alignment unit tests."
_SCHEMA_ENTRY = [{"taskType": "asr", "request": {}, "response": {}}]

_ULCA_BASE = dict(
    name="my-service",
    description=_LONG_DESCRIPTION,
    modelId="model-1",
    modelVersion="1.0",
    task={"type": "asr"},
    inferenceEndPoint={
        "callbackUrl": "http://localhost:8080",
        "infraDescription": "test-hw-cluster",
        "schema": _SCHEMA_ENTRY,
    },
    costPerUnit=0.01,
    unitSize=1,
    tierIds=["tier-1"],
)

_LEGACY_BASE = dict(
    name="my-service",
    serviceDescription=_LONG_DESCRIPTION,
    hardwareDescription="test-hw-cluster",
    modelId="model-1",
    modelVersion="1.0",
    endpoint="http://localhost:8080",
    taskType="asr",
    inferenceEndPoint={"schema": _SCHEMA_ENTRY},  # no legacy alias for `schema`
    costPerUnit=0.01,
    unitSize=1,
    tierIds=["tier-1"],
)


def _make_svc() -> "ServiceService":
    service_repo = MagicMock()
    service_repo.get_by_name = AsyncMock(return_value=None)
    service_repo.get_by_service_id = AsyncMock(return_value=None)
    service_repo.add = AsyncMock()
    service_repo.commit = AsyncMock()
    service_repo.rollback = AsyncMock()
    service_repo.get_tier_names_by_ids = AsyncMock(return_value={"tier-1": "Tier 1"})

    model_repo = MagicMock()
    model_mock = MagicMock()
    model_mock.inference_endpoint = {}
    model_mock.task = {"type": "asr"}
    model_repo.get_by_id_version = AsyncMock(return_value=model_mock)

    cache = MagicMock()
    cache.invalidate_service = AsyncMock()
    cache.set_service = AsyncMock()

    svc = ServiceService(service_repo=service_repo, model_repo=model_repo, cache=cache)

    async def _noop_validate(**_kwargs):
        pass

    svc._validate_endpoint_for_model = _noop_validate  # type: ignore[method-assign]
    return svc


# ── task / inferenceEndPoint as nested ULCA objects ─────────────────────────


class TestNestedTaskAndInferenceEndPoint:
    def test_full_ulca_shape_is_accepted(self) -> None:
        req = ServiceCreateRequest(serviceId="svc-ulca", **_ULCA_BASE)
        assert req.task.type == "asr"
        assert req.inferenceEndPoint.callbackUrl == "http://localhost:8080"
        assert req.inferenceEndPoint.infraDescription == "test-hw-cluster"
        assert req.inferenceEndPoint.endpoint_schema == _SCHEMA_ENTRY

    def test_full_ulca_shape_backfills_deprecated_flat_aliases(self) -> None:
        """Downstream code (service_service.py) still reads the flat
        aliases for the pre-existing fields — they must be populated
        regardless of which input channel the caller used."""
        req = ServiceCreateRequest(serviceId="svc-ulca", **_ULCA_BASE)
        assert req.taskType == "asr"
        assert req.endpoint == "http://localhost:8080"
        assert req.hardwareDescription == "test-hw-cluster"

    def test_legacy_flat_aliases_are_accepted_and_reconciled_into_nested_shape(self) -> None:
        req = ServiceCreateRequest(serviceId="svc-legacy", **_LEGACY_BASE)
        assert req.task.type == "asr"
        assert req.inferenceEndPoint.callbackUrl == "http://localhost:8080"
        assert req.inferenceEndPoint.infraDescription == "test-hw-cluster"

    def test_api_key_legacy_alias_becomes_structured_inference_api_key(self) -> None:
        base = {**_LEGACY_BASE, "api_key": "super-secret"}
        req = ServiceCreateRequest(serviceId="svc-legacy", **base)
        assert req.inferenceEndPoint.inferenceApiKey.value == "super-secret"
        assert req.inferenceEndPoint.inferenceApiKey.name == "Authorization"

    def test_missing_task_and_task_type_both_rejected(self) -> None:
        base = {k: v for k, v in _ULCA_BASE.items() if k != "task"}
        with pytest.raises(PydanticValidationError, match="task is required"):
            ServiceCreateRequest(serviceId="svc-1", **base)


# ── description required on create (25-1000 chars) ──────────────────────────


class TestDescriptionRequired:
    def test_missing_description_and_service_description_rejected(self) -> None:
        base = {k: v for k, v in _ULCA_BASE.items() if k != "description"}
        with pytest.raises(PydanticValidationError, match="description is required"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_too_short_description_rejected(self) -> None:
        base = {**_ULCA_BASE, "description": "too short"}
        with pytest.raises(PydanticValidationError, match="25-1000 characters"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_deprecated_service_description_alias_satisfies_requirement(self) -> None:
        base = {k: v for k, v in _ULCA_BASE.items() if k != "description"}
        base["serviceDescription"] = _LONG_DESCRIPTION
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.description == _LONG_DESCRIPTION

    def test_update_description_too_short_when_supplied_is_accepted(self) -> None:
        """The 25-1000 char rule fires on create only (same scoping as
        SERVICE_ID_MIN_LEN_ON_CREATE) — the admin edit form resends the
        stored description on every update, so a pre-existing service with
        a short one must not 422 on an unrelated edit."""
        req = ServiceUpdateRequest(
            serviceId="svc-1",
            description="too short",
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )
        assert req.description == "too short"

    def test_update_without_description_does_not_require_it(self) -> None:
        req = ServiceUpdateRequest(
            serviceId="svc-1", isPublished=True,
        )
        assert req.description is None


# ── inferenceEndPoint required on create (callbackUrl, infraDescription, schema) ──


class TestInferenceEndPointRequired:
    def test_missing_schema_allowed_at_pydantic_level(self) -> None:
        """`schema` requiredness moved to the service layer, so it can be
        derived from the linked model there — see
        TestSchemaDerivationAndTaskTypeConsistency for the actual
        required/derived enforcement. At the Pydantic level, omitting it
        is allowed."""
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            "callbackUrl": "http://localhost:8080",
            "infraDescription": "test-hw-cluster",
        }}
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.inferenceEndPoint.endpoint_schema is None

    def test_missing_callback_url_and_endpoint_rejected(self) -> None:
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            "infraDescription": "test-hw-cluster",
            "schema": _SCHEMA_ENTRY,
        }}
        with pytest.raises(PydanticValidationError, match="callbackUrl"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_missing_infra_description_and_hardware_description_rejected(self) -> None:
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            "callbackUrl": "http://localhost:8080",
            "schema": _SCHEMA_ENTRY,
        }}
        with pytest.raises(PydanticValidationError, match="infraDescription"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_short_infra_description_via_legacy_alias_still_enforces_min_length(self) -> None:
        """The legacy `hardwareDescription` alias must not bypass the
        5-char minimum that a direct `inferenceEndPoint.infraDescription`
        payload would get — merge happens through the constructor, not
        model_copy, specifically to catch this."""
        base = {**_LEGACY_BASE, "hardwareDescription": "hw"}
        with pytest.raises(PydanticValidationError, match="infraDescription"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_schema_entry_missing_task_type_rejected(self) -> None:
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            **_ULCA_BASE["inferenceEndPoint"],
            "schema": [{"request": {}, "response": {}}],
        }}
        with pytest.raises(PydanticValidationError, match="taskType"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_schema_entry_unrecognized_task_type_rejected(self) -> None:
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            **_ULCA_BASE["inferenceEndPoint"],
            "schema": [{"taskType": "not-a-real-task", "request": {}, "response": {}}],
        }}
        with pytest.raises(PydanticValidationError, match="not a recognized task type"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_schema_accepts_ulca_translation_vocabulary(self) -> None:
        """`schema` entries may use ULCA's own discriminator strings
        (translation, txt-lang-detection) even where they differ from our
        TaskTypeEnum values (nmt, language-detection) — task is 'nmt' here
        specifically so this also satisfies the taskType/schema
        cross-check below (nmt <-> translation are equivalent)."""
        base = {**_ULCA_BASE, "task": {"type": "nmt"}, "inferenceEndPoint": {
            **_ULCA_BASE["inferenceEndPoint"],
            "schema": [{"taskType": "translation", "request": {}, "response": {}}],
        }}
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.inferenceEndPoint.endpoint_schema[0]["taskType"] == "translation"

    def test_update_does_not_require_schema_or_infra_description(self) -> None:
        """Partial update — a bare endpoint change must not be forced to
        also supply the ULCA-required-on-create fields."""
        req = ServiceUpdateRequest(
            serviceId="svc-1",
            endpoint="http://new-endpoint",
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )
        assert req.inferenceEndPoint.callbackUrl == "http://new-endpoint"
        assert req.inferenceEndPoint.endpoint_schema is None


# ── schema entries must match the service's own task type (follow-up) ──────


class TestSchemaTaskTypeCrossCheck:
    """Nothing previously stopped a TTS service from shipping an
    `asr`-shaped schema entry — fixed by cross-checking
    inferenceEndPoint.schema against the service's own task.type."""

    def test_mismatched_schema_task_type_rejected_on_create(self) -> None:
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            **_ULCA_BASE["inferenceEndPoint"],
            "schema": [{"taskType": "tts", "request": {}, "response": {}}],
        }}
        with pytest.raises(PydanticValidationError, match="must include at least one entry"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_ulca_equivalent_task_type_is_accepted(self) -> None:
        """Service task 'language-detection' + schema entry
        'txt-lang-detection' are ULCA-equivalent — must not be rejected."""
        base = {**_ULCA_BASE, "task": {"type": "language-detection"}, "inferenceEndPoint": {
            **_ULCA_BASE["inferenceEndPoint"],
            "schema": [{"taskType": "txt-lang-detection", "request": {}, "response": {}}],
        }}
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.taskType == "language-detection"

    def test_mismatch_rejected_on_update_when_both_touched_together(self) -> None:
        with pytest.raises(PydanticValidationError, match="must include at least one entry"):
            ServiceUpdateRequest(
                serviceId="svc-1",
                taskType="tts",
                inferenceEndPoint={"schema": [{"taskType": "asr", "request": {}, "response": {}}]},
                costPerUnit=1.0,
                unitSize=1,
                tierIds=["tier-1"],
            )

    def test_schema_omitted_on_update_skips_cross_check_at_pydantic_level(self) -> None:
        """Nothing to compare against yet at the Pydantic layer when only
        one side is touched — ServiceService.update_service checks that
        case against the stored row instead (see
        TestSchemaDerivationAndTaskTypeConsistency below)."""
        req = ServiceUpdateRequest(
            serviceId="svc-1",
            taskType="tts",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )
        assert req.taskType == "tts"


# ── serviceId minimum length on create only ─────────────────────────────────


class TestServiceIdMinLengthOnCreateOnly:
    def test_short_service_id_rejected_on_create(self) -> None:
        base = {k: v for k, v in _ULCA_BASE.items()}
        with pytest.raises(PydanticValidationError, match="at least 5"):
            ServiceCreateRequest(serviceId="ab1", **base)

    def test_five_char_service_id_accepted_on_create(self) -> None:
        req = ServiceCreateRequest(serviceId="ab123", **_ULCA_BASE)
        assert req.serviceId == "ab123"

    def test_shared_validator_does_not_enforce_min_length(self) -> None:
        """validate_service_id() is also used to validate an existing
        serviceId on GET/DELETE lookups — it must keep accepting
        already-existing short IDs, never touched/migrated."""
        assert validate_service_id("ab") == "ab"


# ── New optional InferenceAPIEndPoint fields reach persistence ──────────────


class TestNewFieldsPersistence:
    @pytest.mark.asyncio
    async def test_create_persists_new_ulca_fields(self) -> None:
        svc = _make_svc()
        base = {
            **_ULCA_BASE,
            "inferenceEndPoint": {
                **_ULCA_BASE["inferenceEndPoint"],
                "isMultilingualEnabled": True,
                "providerName": "Dhruva-Team",
                "inferenceModelId": "model-xyz-123",
                "isSyncApi": True,
            },
        }
        payload = ServiceCreateRequest(serviceId="svc-new-fields", **base)

        await svc.create_service(payload, created_by="user-1")

        instance = svc._services.add.await_args.args[0]
        assert instance.is_multilingual_enabled is True
        assert instance.provider_name == "Dhruva-Team"
        assert instance.inference_model_id == "model-xyz-123"
        assert instance.is_sync_api is True
        assert instance.inference_schema == _SCHEMA_ENTRY

    @pytest.mark.asyncio
    async def test_update_with_inference_endpoint_writes_only_supplied_subfields(self) -> None:
        service_repo = MagicMock()
        instance_mock = MagicMock(
            model_id="model-1", model_version="1.0", api_key=None,
            endpoint="http://existing", task_type="asr",
            # Explicit None, not an unconfigured MagicMock attribute — see
            # test_service_update.py's _make_service_orm for why that
            # distinction matters here.
            inference_schema=None,
        )
        service_repo.get_by_service_id = AsyncMock(return_value=instance_mock)
        service_repo.apply_updates = AsyncMock()
        service_repo.commit = AsyncMock()
        service_repo.get_tier_names_by_ids = AsyncMock(return_value={"tier-1": "Tier 1"})

        model_repo = MagicMock()
        model_repo.get_by_id_version = AsyncMock(return_value=None)

        cache = MagicMock()
        cache.invalidate_service = AsyncMock()
        cache.set_service = AsyncMock()

        svc = ServiceService(service_repo=service_repo, model_repo=model_repo, cache=cache)

        payload = ServiceUpdateRequest(
            serviceId="svc-1",
            inferenceEndPoint={"providerName": "New-Provider"},
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )

        await svc.update_service(payload, updated_by="user-1")

        _, update_data = service_repo.apply_updates.call_args.args
        assert update_data["provider_name"] == "New-Provider"
        # isMultilingualEnabled was never supplied — must NOT be forced to
        # False and reset an existing True.
        assert "is_multilingual_enabled" not in update_data
        # Regression guard: caught live (not by any mocked test) as a real
        # 500 — touching inferenceEndPoint for an unrelated sub-field (here,
        # providerName only, no callbackUrl/infraDescription supplied via
        # either channel) must NOT clobber `endpoint` (NOT NULL — crashes
        # the DB write) or `hardware_description` (nullable — would
        # silently null out an existing value instead) to None.
        assert "endpoint" not in update_data
        assert "hardware_description" not in update_data


# ── Response serialization ───────────────────────────────────────────────────


class TestServiceToDictUlcaShape:
    def _make_service_orm(self) -> MagicMock:
        from datetime import datetime, timezone

        svc = MagicMock()
        svc.service_id = "svc-1"
        svc.name = "my-service"
        svc.service_description = _LONG_DESCRIPTION
        svc.hardware_description = "test-hw-cluster"
        svc.model_id = "model-1"
        svc.model_version = "1.0"
        svc.task_type = "asr"
        svc.endpoint = "http://localhost:8080"
        svc.inference_server_type = "triton"
        svc.ssl_verify = True
        svc.api_key = "super-secret"
        svc.inference_api_key = None
        svc.is_multilingual_enabled = False
        svc.supported_input_formats = None
        svc.supported_output_formats = None
        svc.inference_schema = _SCHEMA_ENTRY
        svc.is_sync_api = True
        svc.async_api_details = None
        svc.provider_name = None
        svc.inference_model_id = None
        svc.health_status = None
        svc.benchmarks = None
        svc.expected_response_schema = None
        svc.is_published = True
        svc.is_try_it_default = False
        svc.published_at = None
        svc.unpublished_at = None
        svc.cost_per_unit = None
        svc.unit_size = None
        svc.unit_rate = None
        svc.tier_ids = None
        svc.deleted_at = None
        svc.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        svc.created_by = "user-1"
        svc.updated_by = "user-1"
        return svc

    def test_description_and_task_and_inference_endpoint_present(self) -> None:
        serializers = importlib.import_module("app.services.model-management.serializers")
        out = serializers.service_to_dict(self._make_service_orm())

        assert out["description"] == _LONG_DESCRIPTION
        assert out["task"] == {"type": "asr"}
        assert out["inferenceEndPoint"]["callbackUrl"] == "http://localhost:8080"
        assert out["inferenceEndPoint"]["infraDescription"] == "test-hw-cluster"
        assert out["inferenceEndPoint"]["schema"] == _SCHEMA_ENTRY

    def test_flat_api_key_stays_unmasked_for_inference_service(self) -> None:
        """Unlike Model's inferenceApiKey, the flat `api_key` field must NOT
        be masked: inference-service reads this exact key off this exact
        response to authenticate the real outbound Triton call
        (services/inference-service/services/base/task_service.py, guarded
        by its own test_triton_url_redaction.py) — there is no other
        source for it. Masking it here breaks every auth-protected Triton
        backend platform-wide."""
        serializers = importlib.import_module("app.services.model-management.serializers")
        out = serializers.service_to_dict(self._make_service_orm())

        assert out["api_key"] == "super-secret"

    def test_nested_inference_api_key_is_masked(self) -> None:
        """The NEW nested `inferenceEndPoint.inferenceApiKey` object is
        masked, matching Model's existing inferenceApiKey handling — safe
        because inference-service never reads this nested field today."""
        serializers = importlib.import_module("app.services.model-management.serializers")
        out = serializers.service_to_dict(self._make_service_orm())

        assert out["inferenceEndPoint"]["inferenceApiKey"]["value"] == "***"
        assert out["inferenceEndPoint"]["inferenceApiKey"]["name"] == "Authorization"

    def test_no_api_key_at_all_yields_none_in_nested_shape_only(self) -> None:
        serializers = importlib.import_module("app.services.model-management.serializers")
        orm = self._make_service_orm()
        orm.api_key = None
        out = serializers.service_to_dict(orm)

        assert out["api_key"] is None
        assert out["inferenceEndPoint"]["inferenceApiKey"] is None


# ── RBAC: inferenceEndPoint hidden from non-admin (carries infraDescription) ─


class TestRbacHidesInferenceEndPoint:
    def test_inference_endpoint_not_in_non_admin_allowlist(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "app.routes.service_ulca_test", "app/routes/service.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        item = {
            "serviceId": "svc-1",
            "description": _LONG_DESCRIPTION,
            "inferenceEndPoint": {"infraDescription": "8x A100 cluster"},
        }
        filtered = mod._filter_service_fields(item)

        assert "inferenceEndPoint" not in filtered
        assert filtered["description"] == _LONG_DESCRIPTION

        assert "inferenceEndPoint" not in filtered


# ── schema derivation from the linked model + update-side consistency ──────


class TestSchemaDerivationAndTaskTypeConsistency:
    @pytest.mark.asyncio
    async def test_create_derives_schema_from_model_when_omitted(self) -> None:
        svc = _make_svc()
        model_schema = {"taskType": "asr", "request": {"a": 1}, "response": {"b": 2}}
        svc._models.get_by_id_version = AsyncMock(
            return_value=MagicMock(
                inference_endpoint={"schema": model_schema}, task={"type": "asr"}
            )
        )
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            "callbackUrl": "http://localhost:8080",
            "infraDescription": "test-hw-cluster",
        }}
        payload = ServiceCreateRequest(serviceId="svc-derived", **base)

        await svc.create_service(payload, created_by="user-1")

        instance = svc._services.add.await_args.args[0]
        assert instance.inference_schema == [model_schema]

    @pytest.mark.asyncio
    async def test_create_derives_schema_backfilling_missing_task_type(self) -> None:
        """Regression: a model's own schema validator only requires
        `model_name` — never `taskType` — so a model registered before
        derivation existed can have a schema with no `taskType` at all.
        Derivation must backfill it from the model's own `task.type`
        rather than failing outright (caught live against a real llm
        service whose model had exactly this shape)."""
        svc = _make_svc()
        model_schema_no_task_type = {
            "model_name": "some-llm-model",
            "request": {"messages": [{"role": "user", "content": "Hello"}]},
            "response": {"choices": [{"message": {"content": "Hi"}}]},
        }
        svc._models.get_by_id_version = AsyncMock(
            return_value=MagicMock(
                inference_endpoint={"schema": model_schema_no_task_type},
                task={"type": "llm"},
            )
        )
        base = {
            **_ULCA_BASE,
            "task": {"type": "llm"},
            "inferenceEndPoint": {
                "callbackUrl": "http://localhost:8080",
                "infraDescription": "test-hw-cluster",
            },
        }
        payload = ServiceCreateRequest(serviceId="svc-backfill", **base)

        await svc.create_service(payload, created_by="user-1")

        instance = svc._services.add.await_args.args[0]
        assert instance.inference_schema == [{**model_schema_no_task_type, "taskType": "llm"}]

    @pytest.mark.asyncio
    async def test_create_raises_when_omitted_and_model_has_no_schema(self) -> None:
        svc = _make_svc()  # _make_svc's model_mock.inference_endpoint == {} — no schema
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            "callbackUrl": "http://localhost:8080",
            "infraDescription": "test-hw-cluster",
        }}
        payload = ServiceCreateRequest(serviceId="svc-no-schema", **base)

        with pytest.raises(ValidationError, match="inferenceEndPoint.schema is required"):
            await svc.create_service(payload, created_by="user-1")

    @pytest.mark.asyncio
    async def test_create_rejects_derived_schema_that_mismatches_task_type(self) -> None:
        """Derivation goes through the exact same taskType cross-check a
        manually-supplied schema gets — a model registered with a
        mismatched schema can't silently poison a new service."""
        svc = _make_svc()
        model_schema = {"taskType": "tts", "request": {}, "response": {}}
        svc._models.get_by_id_version = AsyncMock(
            return_value=MagicMock(
                inference_endpoint={"schema": model_schema}, task={"type": "asr"}
            )
        )
        base = {**_ULCA_BASE, "inferenceEndPoint": {
            "callbackUrl": "http://localhost:8080",
            "infraDescription": "test-hw-cluster",
        }}
        payload = ServiceCreateRequest(serviceId="svc-mismatch", **base)  # task = asr

        with pytest.raises(ValidationError, match="must include at least one entry"):
            await svc.create_service(payload, created_by="user-1")

    @pytest.mark.asyncio
    async def test_update_rejects_new_task_type_that_mismatches_existing_schema(self) -> None:
        """The one taskType/schema-mismatch scenario reachable through the
        real API: taskType is being changed (required whenever any
        substantive edit happens) while inferenceEndPoint isn't touched at
        all — so the OLD, now-mismatched schema is still the one on file."""
        service_repo = MagicMock()
        instance_mock = MagicMock(
            model_id="model-1", model_version="1.0", api_key=None,
            endpoint="http://existing", task_type="asr",
            inference_schema=_SCHEMA_ENTRY,  # [{"taskType": "asr", ...}]
        )
        service_repo.get_by_service_id = AsyncMock(return_value=instance_mock)
        service_repo.get_tier_names_by_ids = AsyncMock(return_value={"tier-1": "Tier 1"})
        model_repo = MagicMock()
        cache = MagicMock()
        svc = ServiceService(service_repo=service_repo, model_repo=model_repo, cache=cache)

        payload = ServiceUpdateRequest(
            serviceId="svc-1",
            taskType="tts",  # existing schema on file is asr-shaped
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )

        with pytest.raises(ValidationError, match="must include at least one entry"):
            await svc.update_service(payload, updated_by="user-1")

    def test_consistency_helper_skips_when_neither_side_touched(self) -> None:
        """Regression guard: a plain, unrelated update (e.g. isPublished)
        on a legacy row whose stored task/schema predate this check must
        not be rejected just because the row's OWN old data doesn't
        satisfy today's rule."""
        service_repo, model_repo, cache = MagicMock(), MagicMock(), MagicMock()
        svc = ServiceService(service_repo=service_repo, model_repo=model_repo, cache=cache)

        svc._validate_schema_task_type_consistency_on_update(
            new_task_type=None,
            new_schema=None,
            existing_task_type="asr",
            existing_schema=[{"taskType": "tts", "request": {}, "response": {}}],
        )  # must not raise

    def test_consistency_helper_skips_when_both_sides_touched(self) -> None:
        """Both-touched-together is already validated by
        ServiceUpdateRequest's own Pydantic-level check — re-checking here
        would just be redundant."""
        service_repo, model_repo, cache = MagicMock(), MagicMock(), MagicMock()
        svc = ServiceService(service_repo=service_repo, model_repo=model_repo, cache=cache)

        svc._validate_schema_task_type_consistency_on_update(
            new_task_type="tts",
            new_schema=[{"taskType": "asr", "request": {}, "response": {}}],
            existing_task_type="asr",
            existing_schema=_SCHEMA_ENTRY,
        )  # must not raise, even though the two mismatch

    def test_consistency_helper_catches_schema_only_change_against_existing_task_type(self) -> None:
        """Not reachable via the public API today (any inferenceEndPoint
        edit must resend taskType too, per the billing-fields-required-
        together rule), but the helper is written to handle it correctly
        regardless — e.g. if that rule is ever relaxed, or for any internal
        caller that bypasses it."""
        service_repo, model_repo, cache = MagicMock(), MagicMock(), MagicMock()
        svc = ServiceService(service_repo=service_repo, model_repo=model_repo, cache=cache)

        with pytest.raises(ValidationError, match="must include at least one entry"):
            svc._validate_schema_task_type_consistency_on_update(
                new_task_type=None,
                new_schema=[{"taskType": "tts", "request": {}, "response": {}}],
                existing_task_type="asr",
                existing_schema=None,
            )
