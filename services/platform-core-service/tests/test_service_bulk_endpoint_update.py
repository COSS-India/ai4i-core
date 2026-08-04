"""Unit tests: ServiceService.update_service_endpoints (bulk PATCH /services).

Covers the "services": [{"serviceId", "endpoint"}, ...] bulk-update path
added alongside the existing single-object PATCH /services behavior, which
must remain unaffected (see test_service_update.py).
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

import importlib

# ── Module-level stubs (mirrors test_service_update.py) ──────────────────────


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

from app.core.exceptions import EntityNotFoundError
from app.schemas.model_management.service import ServiceEndpointUpdateItem

# model-management directory is hyphenated; plain imports cannot resolve it.
_service_service_module = importlib.import_module(
    "app.services.model-management.service_service"
)
ServiceService = _service_service_module.ServiceService
EndpointValidationFailedError = _service_service_module.EndpointValidationFailedError


def _make_service_orm(service_id: str) -> MagicMock:
    instance = MagicMock()
    instance.service_id = service_id
    instance.model_id = "model-1"
    instance.model_version = "1.0"
    instance.api_key = None
    instance.tier_ids = []
    return instance


def _make_svc(instances_by_id: dict) -> ServiceService:
    service_repo = MagicMock()
    service_repo.get_by_service_id = AsyncMock(
        side_effect=lambda sid: instances_by_id.get(sid)
    )
    service_repo.apply_updates = AsyncMock()
    service_repo.commit = AsyncMock()
    service_repo.rollback = AsyncMock()
    service_repo.get_tier_names_by_ids = AsyncMock(return_value={})

    model_repo = MagicMock()
    model_repo.get_by_id_version = AsyncMock(return_value=MagicMock(inference_endpoint={}, task={}))

    cache = MagicMock()
    cache.invalidate_service = AsyncMock()
    cache.set_service = AsyncMock()

    svc = ServiceService(service_repo=service_repo, model_repo=model_repo, cache=cache)
    svc._validate_endpoint_for_model = AsyncMock()
    return svc


class TestUpdateServiceEndpointsBulk:
    @pytest.mark.asyncio
    async def test_bulk_update_all_succeed(self) -> None:
        instances = {
            "svc-a": _make_service_orm("svc-a"),
            "svc-b": _make_service_orm("svc-b"),
        }
        svc = _make_svc(instances)
        items = [
            ServiceEndpointUpdateItem(serviceId="svc-a", endpoint="http://host-a:8000"),
            ServiceEndpointUpdateItem(serviceId="svc-b", endpoint="http://host-b:8000"),
        ]

        updated_ids = await svc.update_service_endpoints(items, updated_by="user-1")

        assert updated_ids == ["svc-a", "svc-b"]
        assert svc._services.apply_updates.await_count == 2
        svc._services.commit.assert_awaited_once()
        svc._services.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_update_unknown_service_id_rolls_back_batch(self) -> None:
        instances = {"svc-a": _make_service_orm("svc-a")}
        svc = _make_svc(instances)
        items = [
            ServiceEndpointUpdateItem(serviceId="svc-a", endpoint="http://host-a:8000"),
            ServiceEndpointUpdateItem(serviceId="svc-missing", endpoint="http://host-b:8000"),
        ]

        with pytest.raises(EntityNotFoundError):
            await svc.update_service_endpoints(items, updated_by="user-1")

        svc._services.apply_updates.assert_not_called()
        svc._services.commit.assert_not_called()

    def test_bulk_request_accepts_max_items(self) -> None:
        from app.schemas.model_management.service import (
            ServiceBulkEndpointUpdateRequest,
        )

        items = [
            {"serviceId": f"svc-{i}", "endpoint": f"http://host-{i}:8000"}
            for i in range(50)
        ]

        request = ServiceBulkEndpointUpdateRequest(services=items)

        assert len(request.services) == 50

    def test_bulk_request_rejects_over_max_items(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from app.schemas.model_management.service import (
            ServiceBulkEndpointUpdateRequest,
        )

        items = [
            {"serviceId": f"svc-{i}", "endpoint": f"http://host-{i}:8000"}
            for i in range(51)
        ]

        with pytest.raises(PydanticValidationError):
            ServiceBulkEndpointUpdateRequest(services=items)

    @pytest.mark.asyncio
    async def test_single_object_update_still_requires_serviceId(self) -> None:
        """Guards the schema disambiguation: a bulk item without a
        top-level "services" key must not be routable as a bulk request."""
        from pydantic import ValidationError as PydanticValidationError

        from app.schemas.model_management.service import (
            ServiceBulkEndpointUpdateRequest,
        )

        with pytest.raises(PydanticValidationError):
            ServiceBulkEndpointUpdateRequest(serviceId="svc-a", endpoint="http://host-a:8000")

    @pytest.mark.asyncio
    async def test_bulk_update_probe_failure_on_second_item_writes_nothing(self) -> None:
        """A validation failure on any item (probe or lookup) happens before
        the write phase, so nothing is applied and there is nothing to roll
        back — the batch is all-or-nothing at the validation stage too."""
        instances = {
            "svc-a": _make_service_orm("svc-a"),
            "svc-b": _make_service_orm("svc-b"),
        }
        svc = _make_svc(instances)
        svc._validate_endpoint_for_model = AsyncMock(
            side_effect=[
                None,
                EndpointValidationFailedError("svc-b unreachable", ["unreachable"]),
            ]
        )
        items = [
            ServiceEndpointUpdateItem(serviceId="svc-a", endpoint="http://host-a:8000"),
            ServiceEndpointUpdateItem(serviceId="svc-b", endpoint="http://host-b:8000"),
        ]

        with pytest.raises(EndpointValidationFailedError):
            await svc.update_service_endpoints(items, updated_by="user-1")

        svc._services.apply_updates.assert_not_called()
        svc._services.commit.assert_not_called()
        svc._services.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_update_commit_failure_rolls_back_batch(self) -> None:
        """All items pass validation and apply_updates, but commit() itself
        fails — the whole batch must roll back, not just the last item."""
        instances = {
            "svc-a": _make_service_orm("svc-a"),
            "svc-b": _make_service_orm("svc-b"),
        }
        svc = _make_svc(instances)
        svc._services.commit = AsyncMock(side_effect=RuntimeError("db connection lost"))
        items = [
            ServiceEndpointUpdateItem(serviceId="svc-a", endpoint="http://host-a:8000"),
            ServiceEndpointUpdateItem(serviceId="svc-b", endpoint="http://host-b:8000"),
        ]

        with pytest.raises(RuntimeError):
            await svc.update_service_endpoints(items, updated_by="user-1")

        assert svc._services.apply_updates.await_count == 2
        svc._services.rollback.assert_awaited_once()


import importlib.util

# app/routes/__init__.py eagerly imports every route module plus
# ai4i_core.bootstrap.versioning, which this suite's conftest doesn't stub —
# load service.py directly by file path instead (mirrors test_service_rbac_filtering.py).
_route_spec = importlib.util.spec_from_file_location(
    "app.routes.service", "app/routes/service.py"
)
_service_route_mod = importlib.util.module_from_spec(_route_spec)
sys.modules["app.routes.service"] = _service_route_mod
_route_spec.loader.exec_module(_service_route_mod)

update_service = _service_route_mod.update_service


class TestUpdateServiceRouteDispatch:
    """PATCH /services must keep routing a plain single-object body to
    ServiceService.update_service, unaffected by the new bulk branch."""

    @pytest.mark.asyncio
    async def test_single_object_payload_reaches_update_service(self) -> None:
        from app.schemas.model_management.service import ServiceUpdateRequest

        request = MagicMock()
        request.headers.get.return_value = "user-1"
        payload = ServiceUpdateRequest(serviceId="svc-a", isPublished=True)

        svc = MagicMock()
        svc.update_service = AsyncMock(return_value=None)
        svc.update_service_endpoints = AsyncMock()

        await update_service(request, payload, svc=svc)

        svc.update_service.assert_awaited_once_with(payload, updated_by="user-1")
        svc.update_service_endpoints.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_payload_reaches_update_service_endpoints(self) -> None:
        from app.schemas.model_management.service import (
            ServiceBulkEndpointUpdateRequest,
        )

        request = MagicMock()
        request.headers.get.return_value = "user-1"
        payload = ServiceBulkEndpointUpdateRequest(
            services=[{"serviceId": "svc-a", "endpoint": "http://host-a:8000"}]
        )

        svc = MagicMock()
        svc.update_service = AsyncMock()
        svc.update_service_endpoints = AsyncMock(return_value=["svc-a"])

        await update_service(request, payload, svc=svc)

        svc.update_service_endpoints.assert_awaited_once_with(
            payload.services, updated_by="user-1"
        )
        svc.update_service.assert_not_called()
