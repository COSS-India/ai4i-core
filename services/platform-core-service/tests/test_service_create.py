"""Unit tests: serviceId validator and DuplicateServiceIdError (AI4IDS-2495).

Covers:
- ServiceCreateRequest._validate_service_id rejects blank / invalid chars
- ServiceService.create_service raises DuplicateServiceIdError when the ID
  is already taken
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
import importlib

# ── Module-level stubs ────────────────────────────────────────────────────────


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


def _stub_svc(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


# Only stand in for modules genuinely absent — never clobber a real module a
# previously-collected test file already imported (that would corrupt it for
# every test after this one in the same pytest process).
_newly_stubbed = [n for n in _STUBBED_MODULE_NAMES if n not in sys.modules]

_stub_svc("app.models")
_stub_svc("app.models.model_management")
_stub_svc("app.models.model_management.service", Service=MagicMock)
_stub_svc("app.models.model_management.model", Model=MagicMock)
_stub_svc("app.repositories")
_stub_svc("app.repositories.model_management")
_stub_svc("app.repositories.model_management.model_repository", ModelRepository=MagicMock)
_stub_svc("app.repositories.model_management.service_repository", ServiceRepository=MagicMock)

# ─────────────────────────────────────────────────────────────────────────────

from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.schemas.model_management.service import (
    ServiceCreateRequest,
    ServiceUpdateRequest,
)

service_service_mod = importlib.import_module(
    "app.services.model-management.service_service"
)
ServiceService = service_service_mod.ServiceService
DuplicateServiceIdError = service_service_mod.DuplicateServiceIdError

# `from X import Y` above already bound the real names into this module's
# namespace — safe to drop our stand-ins now so a test file collected after
# this one gets the real app.models.* / app.repositories.* modules instead of
# these fakes (sys.modules is process-global and outlives this file).
for _name in _newly_stubbed:
    sys.modules.pop(_name, None)


# ── Helpers ───────────────────────────────────────────────────────────────────

# AI4IDS-2710: `description`/`inferenceEndPoint.infraDescription` now
# enforce ULCA's minimum lengths (25 and 5 chars respectively) and
# `inferenceEndPoint.schema` is required with no legacy alias — so the base
# fixture needs a long-enough description/hardwareDescription plus an
# explicit schema even though it still exercises the deprecated flat
# `serviceDescription`/`hardwareDescription`/`endpoint`/`taskType` aliases
# everywhere else.
_VALID_BASE = dict(
    name="my-service",
    serviceDescription="A test service used for automated unit tests.",
    hardwareDescription="test-hw-cluster",
    modelId="model-1",
    modelVersion="1.0",
    endpoint="http://localhost:8080",
    taskType="asr",
    inferenceEndPoint={"schema": [{"taskType": "asr", "request": {}, "response": {}}]},
    costPerUnit=0.01,
    unitSize=1,
    tierIds=["tier-1"],
    expectedResponseSchema={"output": [{"source": "test"}]},
)


def _make_svc(existing_service_id: str | None = None) -> ServiceService:
    service_repo = MagicMock()
    service_repo.get_by_name = AsyncMock(return_value=None)
    service_repo.get_by_service_id = AsyncMock(
        return_value=MagicMock() if existing_service_id else None
    )
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

    return ServiceService(
        service_repo=service_repo,
        model_repo=model_repo,
        cache=cache,
    )


# ── serviceId validator ───────────────────────────────────────────────────────


class TestServiceIdValidator:
    def test_valid_alphanumeric(self) -> None:
        req = ServiceCreateRequest(serviceId="my-service-123", **_VALID_BASE)
        assert req.serviceId == "my-service-123"

    def test_valid_with_slash_and_underscore(self) -> None:
        req = ServiceCreateRequest(serviceId="org/team_service-1", **_VALID_BASE)
        assert req.serviceId == "org/team_service-1"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(PydanticValidationError, match="serviceId must not be empty"):
            ServiceCreateRequest(serviceId="", **_VALID_BASE)

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(PydanticValidationError, match="serviceId must not be empty"):
            ServiceCreateRequest(serviceId="   ", **_VALID_BASE)

    def test_rejects_special_characters(self) -> None:
        with pytest.raises(PydanticValidationError, match="serviceId must contain only"):
            ServiceCreateRequest(serviceId="bad id!", **_VALID_BASE)

    def test_rejects_dot(self) -> None:
        with pytest.raises(PydanticValidationError, match="serviceId must contain only"):
            ServiceCreateRequest(serviceId="service.name", **_VALID_BASE)


# ── taskType / costPerUnit / unitSize required + validated on create (AI4IDS-2518/2519/2520/2521) ──


class TestCreateRequiredFields:
    def test_missing_task_type_rejected(self) -> None:
        base = {k: v for k, v in _VALID_BASE.items() if k != "taskType"}
        with pytest.raises(PydanticValidationError, match="taskType"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_invalid_task_type_enum_rejected(self) -> None:
        base = {**_VALID_BASE, "taskType": "not-a-real-task-type"}
        with pytest.raises(PydanticValidationError, match="Invalid task type"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_task_type_is_case_insensitive(self) -> None:
        base = {**_VALID_BASE, "taskType": "ASR"}
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.taskType == "asr"

    def test_missing_cost_per_unit_rejected(self) -> None:
        base = {k: v for k, v in _VALID_BASE.items() if k != "costPerUnit"}
        with pytest.raises(PydanticValidationError, match="costPerUnit"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_negative_cost_per_unit_rejected(self) -> None:
        base = {**_VALID_BASE, "costPerUnit": -1.0}
        with pytest.raises(PydanticValidationError):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_zero_cost_per_unit_allowed(self) -> None:
        base = {**_VALID_BASE, "costPerUnit": 0}
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.costPerUnit == 0

    def test_missing_unit_size_rejected(self) -> None:
        base = {k: v for k, v in _VALID_BASE.items() if k != "unitSize"}
        with pytest.raises(PydanticValidationError, match="unitSize"):
            ServiceCreateRequest(serviceId="svc-1", **base)


# ── expectedResponseSchema is optional; falls back to a task-type default
# when omitted (AI4IDS-1844 PR review) — see app.utils.probe_payloads ──


class TestExpectedResponseSchemaOptional:
    def test_omitted_on_create_defaults_to_none(self) -> None:
        """Not required — endpoint_validator falls back to a built-in
        per-task-type shape (or skips the check) when this is None."""
        base = {k: v for k, v in _VALID_BASE.items() if k != "expectedResponseSchema"}
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.expectedResponseSchema is None

    def test_explicit_value_on_create_is_kept(self) -> None:
        req = ServiceCreateRequest(serviceId="svc-1", **_VALID_BASE)
        assert req.expectedResponseSchema == {"output": [{"source": "test"}]}

    def test_empty_dict_rejected_when_explicitly_supplied(self) -> None:
        base = {**_VALID_BASE, "expectedResponseSchema": {}}
        with pytest.raises(PydanticValidationError, match="non-empty object"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_omitted_on_update_is_none(self) -> None:
        req = ServiceUpdateRequest(
            serviceId="svc-1",
            endpoint="http://x",
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )
        assert req.expectedResponseSchema is None

    def test_empty_dict_rejected_on_update_when_supplied(self) -> None:
        with pytest.raises(PydanticValidationError, match="non-empty object"):
            ServiceUpdateRequest(serviceId="svc-1", expectedResponseSchema={})


# ── Same value validators apply on update, but fields stay optional (AI4IDS-2528/2529) ──


class TestUpdateValueValidators:
    def test_invalid_task_type_enum_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="Invalid task type"):
            ServiceUpdateRequest(serviceId="svc-1", taskType="bogus")

    def test_negative_cost_per_unit_rejected(self) -> None:
        with pytest.raises(
            PydanticValidationError, match="greater than or equal to 0"
        ):
            ServiceUpdateRequest(serviceId="svc-1", costPerUnit=-5)

    def test_publish_only_update_is_exempt(self) -> None:
        """Publish/unpublish-only PATCH calls must not be forced to resend
        taskType/costPerUnit/unitSize/tierIds — that flow sends only
        {serviceId, isPublished} by design (AI4IDS-2524/2525/2526/2527)."""
        req = ServiceUpdateRequest(serviceId="svc-1", isPublished=True)
        assert req.model_dump(exclude_unset=True) == {
            "serviceId": "svc-1",
            "isPublished": True,
        }

    def test_serviceid_only_noop_still_parses(self) -> None:
        """No other field touched -> exempt too (service layer separately
        rejects a true no-op update with its own 'nothing to update' error)."""
        req = ServiceUpdateRequest(serviceId="svc-1")
        assert req.model_dump(exclude_unset=True) == {"serviceId": "svc-1"}


class TestUpdateRequiresBillingFieldsTogether:
    """AI4IDS-2524/2525/2526/2527: any substantive edit (anything beyond the
    publish/unpublish toggle) must resend taskType/costPerUnit/unitSize/tierIds
    together — but the publish/unpublish toggle itself stays exempt, since
    forcing them there would break that flow (see PR #1171's revert of the
    same over-broad requirement on tierIds alone)."""

    def test_editing_endpoint_alone_is_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="must be provided together"):
            ServiceUpdateRequest(serviceId="svc-1", endpoint="http://x")

    def test_editing_endpoint_with_all_four_fields_succeeds(self) -> None:
        req = ServiceUpdateRequest(
            serviceId="svc-1",
            endpoint="http://x",
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )
        assert req.endpoint == "http://x"

    def test_editing_endpoint_with_only_some_of_the_four_is_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="costPerUnit, unitSize, tierIds"):
            ServiceUpdateRequest(serviceId="svc-1", endpoint="http://x", taskType="asr")

    def test_publish_plus_another_field_is_not_exempt(self) -> None:
        """isPublished alongside any other real edit is NOT the publish-only
        case — the four fields are still required."""
        with pytest.raises(PydanticValidationError, match="must be provided together"):
            ServiceUpdateRequest(serviceId="svc-1", isPublished=True, endpoint="http://x")


# ── tierIds must reference existing tiers (AI4IDS-2523/2530) ────────────────


class TestTierIdsExistenceCheck:
    @pytest.mark.asyncio
    async def test_create_rejects_nonexistent_tier_id(self) -> None:
        svc = _make_svc()
        svc._services.get_tier_names_by_ids = AsyncMock(return_value={})

        async def _noop_validate(**_kwargs):
            pass

        svc._validate_endpoint_for_model = _noop_validate  # type: ignore[method-assign]

        base = {**_VALID_BASE, "tierIds": ["ghost-tier"]}
        payload = ServiceCreateRequest(serviceId="svc-1", **base)

        with pytest.raises(ValidationError, match="nonexistent tier"):
            await svc.create_service(payload, created_by="user-1")

    @pytest.mark.asyncio
    async def test_update_rejects_nonexistent_tier_id(self) -> None:
        svc = _make_svc()
        svc._services.get_tier_names_by_ids = AsyncMock(return_value={})
        svc._services.get_by_service_id = AsyncMock(return_value=MagicMock(
            model_id="model-1", model_version="1.0", api_key=None,
        ))

        payload = ServiceUpdateRequest(
            serviceId="svc-1",
            tierIds=["ghost-tier"],
            taskType="asr",
            costPerUnit=1.0,
            unitSize=1,
        )

        with pytest.raises(ValidationError, match="nonexistent tier"):
            await svc.update_service(payload, updated_by="user-1")


# ── DuplicateServiceIdError path ─────────────────────────────────────────────


class TestCreateServiceDuplicateId:
    @pytest.mark.asyncio
    async def test_raises_when_service_id_already_exists(self) -> None:
        svc = _make_svc(existing_service_id="existing-id")

        # Patch endpoint validation to skip the live probe
        async def _noop_validate(**_kwargs):
            pass

        svc._validate_endpoint_for_model = _noop_validate  # type: ignore[method-assign]

        payload = ServiceCreateRequest(serviceId="existing-id", **_VALID_BASE)

        with pytest.raises(DuplicateServiceIdError):
            await svc.create_service(payload, created_by="user-1")

    @pytest.mark.asyncio
    async def test_does_not_raise_when_service_id_is_new(self) -> None:
        svc = _make_svc(existing_service_id=None)

        async def _noop_validate(**_kwargs):
            pass

        svc._validate_endpoint_for_model = _noop_validate  # type: ignore[method-assign]

        payload = ServiceCreateRequest(serviceId="brand-new-id", **_VALID_BASE)

        # Should not raise — we just verify the repo add was called
        await svc.create_service(payload, created_by="user-1")

        svc._services.add.assert_awaited_once()
        svc._services.commit.assert_awaited_once()


# ── _extract_validation_params reads both adapterConfig spellings (PR review) ─
# Migration a1f2e3d4c5b6 writes adapter_config (snake_case) into this same
# inference_endpoint blob; inference_server_resolver.py already reads both
# spellings for exactly that reason — a card stored snake_case must not
# silently yield model_name=None here.


class TestExtractValidationParamsAdapterConfigSpelling:
    def test_camel_case_adapter_config_is_read(self) -> None:
        params = service_service_mod._extract_validation_params(
            {"adapterConfig": {"model_name": "google/gemma-4-31B-it"}}
        )
        assert params["model_name"] == "google/gemma-4-31B-it"

    def test_snake_case_adapter_config_is_also_read(self) -> None:
        params = service_service_mod._extract_validation_params(
            {"adapter_config": {"model_name": "google/gemma-4-31B-it"}}
        )
        assert params["model_name"] == "google/gemma-4-31B-it"

    def test_camel_case_takes_precedence_when_both_present(self) -> None:
        params = service_service_mod._extract_validation_params(
            {
                "adapterConfig": {"model_name": "camel-case-value"},
                "adapter_config": {"model_name": "snake-case-value"},
            }
        )
        assert params["model_name"] == "camel-case-value"

    def test_neither_spelling_present_yields_none(self) -> None:
        params = service_service_mod._extract_validation_params({})
        assert params["model_name"] is None
