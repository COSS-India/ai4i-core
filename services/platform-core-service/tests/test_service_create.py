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

_VALID_BASE = dict(
    name="my-service",
    version="v1",
    description="A sufficiently detailed service description for tests.",
    refUrl="https://github.com/ai4bharat/example",
    task={"type": "asr"},
    languages=[{"sourceLanguage": "en", "targetLanguage": "hi"}],
    license="MIT",
    domain=["general"],
    submitter={"name": "AI4Bharat"},
    trainingDataset={"description": "Internal training corpus for the ASR model."},
    inferenceEndPoint={"callbackUrl": "http://localhost:8080", "schema": []},
    hardwareDescription="hw",
    modelId="model-1",
    modelVersion="1.0",
    costPerUnit=0.01,
    unitSize=1,
    tierIds=["tier-1"],
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


# ── ULCA minLength/maxLength constraints (name/version/description/refUrl) ──


class TestUlcaLengthConstraints:
    def test_name_too_short_rejected(self) -> None:
        base = {**_VALID_BASE, "name": "ab"}
        with pytest.raises(PydanticValidationError, match="at least 5 characters"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_name_too_long_rejected(self) -> None:
        base = {**_VALID_BASE, "name": "a" * 101}
        with pytest.raises(PydanticValidationError, match="at most 100 characters"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_version_too_long_rejected(self) -> None:
        base = {**_VALID_BASE, "version": "v" * 21}
        with pytest.raises(PydanticValidationError, match="at most 20 characters"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_description_too_short_rejected(self) -> None:
        base = {**_VALID_BASE, "description": "too short"}
        with pytest.raises(PydanticValidationError, match="at least 25 characters"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_description_too_long_rejected(self) -> None:
        base = {**_VALID_BASE, "description": "a" * 1001}
        with pytest.raises(PydanticValidationError, match="at most 1000 characters"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_ref_url_too_short_rejected(self) -> None:
        base = {**_VALID_BASE, "refUrl": "abc"}
        with pytest.raises(PydanticValidationError, match="at least 5 characters"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_ref_url_too_long_rejected(self) -> None:
        base = {**_VALID_BASE, "refUrl": "https://" + "a" * 200}
        with pytest.raises(PydanticValidationError, match="at most 200 characters"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_ref_url_omitted_is_valid(self) -> None:
        base = {k: v for k, v in _VALID_BASE.items() if k != "refUrl"}
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.refUrl is None


# ── task / costPerUnit / unitSize required + validated on create (AI4IDS-2518/2519/2520/2521) ──


class TestCreateRequiredFields:
    def test_missing_task_rejected(self) -> None:
        base = {k: v for k, v in _VALID_BASE.items() if k != "task"}
        with pytest.raises(PydanticValidationError, match="task"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_invalid_task_type_enum_rejected(self) -> None:
        base = {**_VALID_BASE, "task": {"type": "not-a-real-task-type"}}
        with pytest.raises(PydanticValidationError, match="Invalid task type"):
            ServiceCreateRequest(serviceId="svc-1", **base)

    def test_task_type_is_case_insensitive(self) -> None:
        base = {**_VALID_BASE, "task": {"type": "ASR"}}
        req = ServiceCreateRequest(serviceId="svc-1", **base)
        assert req.task.type == "asr"

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


# ── Same value validators apply on update, but fields stay optional (AI4IDS-2528/2529) ──


class TestUpdateValueValidators:
    def test_invalid_task_type_enum_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="Invalid task type"):
            ServiceUpdateRequest(serviceId="svc-1", task={"type": "bogus"})

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
    publish/unpublish toggle) must resend task/costPerUnit/unitSize/tierIds
    together — but the publish/unpublish toggle itself stays exempt, since
    forcing them there would break that flow (see PR #1171's revert of the
    same over-broad requirement on tierIds alone)."""

    def test_editing_endpoint_alone_is_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="must be provided together"):
            ServiceUpdateRequest(
                serviceId="svc-1", inferenceEndPoint={"callbackUrl": "http://x", "schema": []}
            )

    def test_editing_endpoint_with_all_four_fields_succeeds(self) -> None:
        req = ServiceUpdateRequest(
            serviceId="svc-1",
            inferenceEndPoint={"callbackUrl": "http://x", "schema": []},
            task={"type": "asr"},
            costPerUnit=1.0,
            unitSize=1,
            tierIds=["tier-1"],
        )
        assert req.inferenceEndPoint.callbackUrl == "http://x"

    def test_editing_endpoint_with_only_some_of_the_four_is_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="costPerUnit, unitSize, tierIds"):
            ServiceUpdateRequest(
                serviceId="svc-1",
                inferenceEndPoint={"callbackUrl": "http://x", "schema": []},
                task={"type": "asr"},
            )

    def test_publish_plus_another_field_is_not_exempt(self) -> None:
        """isPublished alongside any other real edit is NOT the publish-only
        case — the four fields are still required."""
        with pytest.raises(PydanticValidationError, match="must be provided together"):
            ServiceUpdateRequest(
                serviceId="svc-1",
                isPublished=True,
                inferenceEndPoint={"callbackUrl": "http://x", "schema": []},
            )


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
            model_id="model-1", model_version="1.0",
        ))

        payload = ServiceUpdateRequest(
            serviceId="svc-1",
            tierIds=["ghost-tier"],
            task={"type": "asr"},
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
