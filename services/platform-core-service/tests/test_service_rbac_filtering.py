"""Unit tests: GET /services responses are field-filtered for non-admin and
public callers instead of being blocked outright (AI4IDS-1816).

service.read is deliberately granted to every role (Admin, Moderator, Tenant
Admin, User, Guest) because every inference-submission flow depends on this
endpoint to resolve a serviceId — a 403 for non-admin roles would break
inference platform-wide. The actual defect was that the unfiltered response
exposes api_key, policy, and billing/health/hardware internals to every
caller, including the fully public try-it endpoint.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# app/routes/__init__.py eagerly imports every route module plus
# ai4i_core.bootstrap.versioning, which this suite's conftest doesn't stub —
# load service.py directly by file path instead.
_spec = importlib.util.spec_from_file_location(
    "app.routes.service", "app/routes/service.py"
)
_service_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.service"] = _service_route_mod
_spec.loader.exec_module(_service_route_mod)

_filter_service_fields = _service_route_mod._filter_service_fields
_is_platform_admin = _service_route_mod._is_platform_admin
list_services = _service_route_mod.list_services
view_service = _service_route_mod.view_service
list_try_it_services = _service_route_mod.list_try_it_services


def _make_request(permission_ids: str = "") -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": permission_ids}
    return request


_FULL_SERVICE = {
    "serviceId": "svc-1",
    "name": "ASR Prod",
    "modelId": "model-1",
    "modelVersion": "1.0",
    "serviceDescription": "desc",
    "endpoint": "http://internal-host/asr",
    "taskType": "asr",
    "isPublished": True,
    "task": {"type": "asr"},
    "languages": [{"sourceLanguage": "en"}],
    "versionStatus": "ACTIVE",
    "api_key": "super-secret-key",
    "policy": {"accuracy": "sensitive", "cost": "tier_1"},
    "healthStatus": "healthy",
    "benchmarks": {"p99": 120},
    "hardwareDescription": "8x A100",
    "costPerUnit": 0.5,
    "unitSize": 1,
    "unitRate": 0.5,
    "tierIds": ["tier-1"],
    "tierNames": ["Gold"],
    "inferenceServerType": "triton",
    "sslVerify": True,
    "publishedAt": "2026-01-01T00:00:00Z",
    "unpublishedAt": None,
    "deletedAt": None,
    "createdAt": "2026-01-01T00:00:00Z",
    "createdBy": "user-1",
    "updatedBy": "user-1",
}

_SENSITIVE_FIELDS = {
    "api_key", "policy", "healthStatus", "benchmarks", "hardwareDescription",
    "costPerUnit", "unitSize", "unitRate", "tierIds", "tierNames",
    "inferenceServerType", "sslVerify", "publishedAt", "unpublishedAt",
    "deletedAt", "createdAt", "createdBy", "updatedBy",
}


class TestFilterServiceFields:
    def test_strips_sensitive_fields(self) -> None:
        filtered = _filter_service_fields(_FULL_SERVICE)
        assert not (_SENSITIVE_FIELDS & filtered.keys())

    def test_keeps_inference_needed_fields(self) -> None:
        filtered = _filter_service_fields(_FULL_SERVICE)
        assert filtered == {
            "serviceId": "svc-1",
            "name": "ASR Prod",
            "modelId": "model-1",
            "modelVersion": "1.0",
            "serviceDescription": "desc",
            "endpoint": "http://internal-host/asr",
            "taskType": "asr",
            "isPublished": True,
            "task": {"type": "asr"},
            "languages": [{"sourceLanguage": "en"}],
            "versionStatus": "ACTIVE",
        }


class TestIsPlatformAdmin:
    def test_admin_permission_id_is_admin(self) -> None:
        assert _is_platform_admin(_make_request("1,10,20")) is True

    def test_moderator_permission_id_is_admin(self) -> None:
        assert _is_platform_admin(_make_request("2,10")) is True

    def test_user_permission_ids_not_admin(self) -> None:
        assert _is_platform_admin(_make_request("50,51")) is False

    def test_no_header_not_admin(self) -> None:
        assert _is_platform_admin(_make_request("")) is False


class TestListServicesRoute:
    @pytest.mark.asyncio
    async def test_admin_gets_full_response(self) -> None:
        response = MagicMock()
        response.headers = {}
        svc = MagicMock()
        svc.list_services = AsyncMock(return_value=([_FULL_SERVICE], 1))

        result = await list_services(
            request=_make_request("1"),
            response=response,
            task_type=None,
            is_published=None,
            created_by=None,
            offset=0,
            limit=None,
            svc=svc,
        )

        assert result["data"]["services"][0]["api_key"] == "super-secret-key"

    @pytest.mark.asyncio
    async def test_non_admin_gets_filtered_response(self) -> None:
        response = MagicMock()
        response.headers = {}
        svc = MagicMock()
        svc.list_services = AsyncMock(return_value=([_FULL_SERVICE], 1))

        result = await list_services(
            request=_make_request("50,51"),
            response=response,
            task_type=None,
            is_published=None,
            created_by=None,
            offset=0,
            limit=None,
            svc=svc,
        )

        item = result["data"]["services"][0]
        assert "api_key" not in item
        assert "policy" not in item
        assert item["serviceId"] == "svc-1"


class TestViewServiceRoute:
    @pytest.mark.asyncio
    async def test_non_admin_gets_filtered_detail(self) -> None:
        svc = MagicMock()
        svc.get_service_detail = AsyncMock(return_value=dict(_FULL_SERVICE))

        result = await view_service(
            request=_make_request(""), service_id="svc-1", svc=svc
        )

        assert "api_key" not in result["data"]
        assert result["data"]["serviceId"] == "svc-1"

    @pytest.mark.asyncio
    async def test_admin_gets_full_detail(self) -> None:
        svc = MagicMock()
        svc.get_service_detail = AsyncMock(return_value=dict(_FULL_SERVICE))

        result = await view_service(
            request=_make_request("1"), service_id="svc-1", svc=svc
        )

        assert result["data"]["api_key"] == "super-secret-key"


class TestTryItServiceListRoute:
    @pytest.mark.asyncio
    async def test_always_filtered_regardless_of_caller(self) -> None:
        """No auth at all on this route — must never return the full shape."""
        svc = MagicMock()
        svc.list_services = AsyncMock(return_value=([_FULL_SERVICE], 1))

        result = await list_try_it_services(task_type="nmt", svc=svc)

        item = result["data"]["services"][0]
        assert "api_key" not in item
        assert "policy" not in item
        assert item["serviceId"] == "svc-1"
