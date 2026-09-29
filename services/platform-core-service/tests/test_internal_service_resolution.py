"""Unit tests for GET /internal/services/{id} — the route inference-service
uses to resolve a service's real (unmasked) credentials, gated on a
shared-secret header. Loaded by file path like test_service_rbac_filtering.py
(app/routes/__init__.py eagerly imports every route module plus
ai4i_core.bootstrap, which this suite's conftest doesn't fully stub)."""

from __future__ import annotations

import importlib.util
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

# internal.py pulls in tier_service.py, which needs ai4i_core.kafka —
# not stubbed by conftest.py since no prior test loaded this module.
if "ai4i_core.kafka" not in sys.modules:
    _kafka_stub = types.ModuleType("ai4i_core.kafka")
    _kafka_stub.publish_admin_event = MagicMock()
    _kafka_stub.is_notification_enabled = MagicMock()
    _kafka_stub.is_notification_enabled_bulk = MagicMock()
    _kafka_stub.check_and_record_actions_bulk = MagicMock()
    _kafka_stub.get_notification_id = MagicMock()
    _kafka_stub.resolve_recipients = MagicMock()
    _kafka_stub.resolve_recipients_bulk = MagicMock()
    sys.modules["ai4i_core.kafka"] = _kafka_stub

_spec = importlib.util.spec_from_file_location(
    "app.routes.internal", "app/routes/internal.py"
)
_internal_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.internal"] = _internal_route_mod
_spec.loader.exec_module(_internal_route_mod)

_require_internal_caller = _internal_route_mod._require_internal_caller
internal_get_service = _internal_route_mod.internal_get_service
settings = _internal_route_mod.settings


class TestRequireInternalCaller:
    @pytest.mark.asyncio
    async def test_rejects_when_no_shared_secret_configured(self, monkeypatch) -> None:
        """A blank/unset secret must never be treated as "any header value
        matches" — the gate is fail-closed, not fail-open."""
        monkeypatch.setattr(settings, "internal_service_shared_secret", None)
        with pytest.raises(HTTPException) as exc_info:
            await _require_internal_caller(x_internal_service_token="")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("token", ["wrong-value", "é"])
    async def test_rejects_wrong_or_non_ascii_token(self, monkeypatch, token) -> None:
        monkeypatch.setattr(settings, "internal_service_shared_secret", "the-real-secret")
        with pytest.raises(HTTPException) as exc_info:
            await _require_internal_caller(x_internal_service_token=token)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_accepts_matching_token(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "internal_service_shared_secret", "the-real-secret")
        await _require_internal_caller(x_internal_service_token="the-real-secret")  # must not raise


class TestInternalGetService:
    @pytest.mark.asyncio
    async def test_returns_unmasked_service_detail(self) -> None:
        """Unlike the public GET /services/{id} (mask_service_secrets
        applied unconditionally), this route hands back exactly what
        ServiceService.get_service_detail returns — real credential values,
        for inference-service's own outbound-header use."""
        svc = MagicMock()
        svc.get_service_detail = AsyncMock(return_value={
            "serviceId": "svc-1",
            "api_key": "super-secret-key",
            "inferenceEndPoint": {"authenticationToken": "sk-vllm-secret"},
        })

        result = await internal_get_service(service_id="svc-1", svc=svc)

        assert result["data"]["api_key"] == "super-secret-key"
        assert result["data"]["inferenceEndPoint"]["authenticationToken"] == "sk-vllm-secret"
