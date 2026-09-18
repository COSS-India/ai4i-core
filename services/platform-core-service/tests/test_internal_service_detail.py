"""
Unit tests: GET /internal/services/{service_id} returns the FULL, unfiltered
service detail (including api_key/inferenceApiKey) regardless of caller
identity — unlike the public GET /api/v1/services/{service_id}
(routes/service.py::view_service), which strips those fields for any caller
without ADMIN/MODERATOR permission IDs (AI4IDS-1816).

This route exists because inference-service's own resolver
(InferenceServerResolver._query_model_management_service) calls out with no
per-request identity at all — it isn't forwarding an end user's request, so
there's no X-Permission-IDS to attach. Hitting the public route always looked
"non-admin" to that filter and silently dropped api_key, so a Triton or vLLM
service configured with an auth token resolved with api_key=None every time,
and inference-service called the upstream model server with no Authorization
header regardless of what was configured.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# conftest.py stubs bare "ai4i_core" (exceptions only) so most route modules
# import without the real ai4i-core package — but app/routes/internal.py
# also pulls in app.services.pay_per_use.tier_service, which needs
# ai4i_core.kafka specifically. That submodule isn't stubbed anywhere else
# (no other test module reaches this import path today), so it's stubbed
# here, scoped to this file, rather than widening the shared conftest stub
# for a dependency only this route module needs.
if "ai4i_core.kafka" not in sys.modules:
    _kafka_stub = types.ModuleType("ai4i_core.kafka")
    _kafka_stub.publish_admin_event = MagicMock()
    _kafka_stub.is_notification_enabled = MagicMock(return_value=False)
    _kafka_stub.check_and_record_actions_bulk = AsyncMock()
    sys.modules["ai4i_core.kafka"] = _kafka_stub

# Same workaround as test_service_rbac_filtering.py: app/routes/__init__.py
# eagerly imports every route module plus ai4i_core.bootstrap.versioning,
# which this suite's conftest doesn't stub — load internal.py directly by
# file path instead of via the app.routes package.
_spec = importlib.util.spec_from_file_location(
    "app.routes.internal", "app/routes/internal.py"
)
_internal_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.internal"] = _internal_route_mod
_spec.loader.exec_module(_internal_route_mod)

get_service_detail_internal = _internal_route_mod.get_service_detail_internal


_FULL_SERVICE = {
    "serviceId": "svc-1",
    "name": "LLM Prod",
    "modelId": "model-1",
    "modelVersion": "1.0",
    "serviceDescription": "desc",
    "endpoint": "http://vllm:8000",
    "taskType": "llm",
    "isPublished": True,
    "task": {"type": "llm"},
    "languages": [],
    "model": {
        "modelId": "model-1",
        "name": "gemma",
        "version": "1.0",
        "task": {"type": "llm"},
        "adapterConfig": {"model_name": "google/gemma-4-E4B-it"},
    },
    "api_key": "sk-super-secret-vllm-token",
    "healthStatus": {"status": "healthy", "lastUpdated": None},
    "benchmarks": None,
    "hardwareDescription": "1x A100",
    "costPerUnit": 0.5,
    "unitSize": 1,
    "unitRate": 0.5,
    "tierIds": ["tier-1"],
    "tierNames": ["Gold"],
    "inferenceServerType": "custom",
    "sslVerify": True,
    "publishedAt": "2026-01-01T00:00:00Z",
    "unpublishedAt": None,
    "deletedAt": None,
    "createdAt": "2026-01-01T00:00:00Z",
    "createdBy": "user-1",
    "updatedBy": "user-1",
}


class TestInternalServiceDetailRoute:
    @pytest.mark.asyncio
    async def test_returns_unfiltered_api_key(self) -> None:
        """The exact bug scenario: an identity-less caller (inference-service)
        must still get api_key back — the public route's RBAC filter must
        not apply here."""
        svc = MagicMock()
        svc.get_service_detail = AsyncMock(return_value=dict(_FULL_SERVICE))

        result = await get_service_detail_internal(service_id="svc-1", svc=svc)

        assert result.data.api_key == "sk-super-secret-vllm-token"

    @pytest.mark.asyncio
    async def test_returns_adapter_config_for_inference_service(self) -> None:
        svc = MagicMock()
        svc.get_service_detail = AsyncMock(return_value=dict(_FULL_SERVICE))

        result = await get_service_detail_internal(service_id="svc-1", svc=svc)

        assert result.data.model.adapterConfig.model_dump(exclude_none=True) == {
            "model_name": "google/gemma-4-E4B-it",
        }

    @pytest.mark.asyncio
    async def test_calls_get_service_detail_with_given_id(self) -> None:
        svc = MagicMock()
        svc.get_service_detail = AsyncMock(return_value=dict(_FULL_SERVICE))

        await get_service_detail_internal(service_id="svc-1", svc=svc)

        svc.get_service_detail.assert_awaited_once_with("svc-1")

    @pytest.mark.asyncio
    async def test_invalid_service_id_raises_validation_error(self) -> None:
        from app.core.exceptions import ValidationError

        svc = MagicMock()
        svc.get_service_detail = AsyncMock(return_value=dict(_FULL_SERVICE))

        with pytest.raises(ValidationError):
            await get_service_detail_internal(service_id="../../etc/passwd", svc=svc)
        svc.get_service_detail.assert_not_awaited()
