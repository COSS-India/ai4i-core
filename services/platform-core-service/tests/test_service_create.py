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


def _stub_svc(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


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

from app.schemas.model_management.service import ServiceCreateRequest

service_service_mod = importlib.import_module(
    "app.services.model-management.service_service"
)
ServiceService = service_service_mod.ServiceService
DuplicateServiceIdError = service_service_mod.DuplicateServiceIdError


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_BASE = dict(
    name="my-service",
    serviceDescription="desc",
    hardwareDescription="hw",
    modelId="model-1",
    modelVersion="1.0",
    endpoint="http://localhost:8080",
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
    service_repo.get_tier_names_by_ids = AsyncMock(return_value={})

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
