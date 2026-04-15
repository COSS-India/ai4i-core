"""
Tests for health pre-flight gate in Model Resolution Middleware.
Verifies that inference is rejected with 503 when backend is unhealthy/unknown.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.responses import Response

from ai4icore_model_management.client import ModelManagementClient
from ai4icore_model_management.middleware import ModelResolutionMiddleware


def _make_request(method: str, path: str, body: bytes):
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    from starlette.requests import Request

    return Request(scope, receive)


@pytest.fixture
def mock_client():
    return MagicMock(spec=ModelManagementClient)


@pytest.fixture
def middleware(mock_client):
    app = MagicMock()
    # Avoid entering the A/B selection branch in dispatch() (not under test here).
    mock_client.select_experiment_variant = AsyncMock(return_value=None)
    mw = ModelResolutionMiddleware(
        app,
        model_management_client=mock_client,
        redis_client=None,
        cache_ttl_seconds=300,
        default_triton_endpoint=None,
        default_triton_api_key=None,
        enabled_paths=["/api/v1"],
        config_service_url="http://config-service:8080",
        health_gate_enabled=True,
        health_gate_timeout_seconds=1.0,
        health_gate_cache_ttl_seconds=3.0,
    )
    return mw


@pytest.mark.asyncio
async def test_health_gate_blocks_unhealthy_before_resolution(middleware):
    service_id = "asr-service"
    middleware._fetch_health_status = AsyncMock(
        return_value={"service_id": service_id, "state": "unhealthy", "last_check": "2026-04-14T00:00:00+00:00"}
    )
    middleware._resolve_service = AsyncMock()

    request = _make_request(
        "POST",
        "/api/v1/asr/inference",
        body=b'{"config":{"serviceId":"asr-service"}}',
    )

    call_next = AsyncMock(return_value=Response("ok", status_code=200))
    resp = await middleware.dispatch(request, call_next)

    assert resp.status_code == 503
    middleware._resolve_service.assert_not_called()
    call_next.assert_not_called()


@pytest.mark.asyncio
async def test_health_gate_allows_degraded_and_proceeds(middleware):
    service_id = "asr-service"
    middleware._fetch_health_status = AsyncMock(
        return_value={"service_id": service_id, "state": "degraded", "last_check": "2026-04-14T00:00:00+00:00"}
    )
    middleware._resolve_service = AsyncMock(return_value=("http://example", "model", MagicMock()))

    request = _make_request(
        "POST",
        "/api/v1/asr/inference",
        body=b'{"config":{"serviceId":"asr-service"}}',
    )
    call_next = AsyncMock(return_value=Response("ok", status_code=200))
    resp = await middleware.dispatch(request, call_next)

    assert resp.status_code == 200
    middleware._resolve_service.assert_called_once()
    call_next.assert_called_once()


@pytest.mark.asyncio
async def test_health_gate_fail_closed_on_error(middleware):
    middleware._fetch_health_status = AsyncMock(side_effect=TimeoutError("boom"))
    middleware._resolve_service = AsyncMock()

    request = _make_request(
        "POST",
        "/api/v1/nmt/inference",
        body=b'{"config":{"serviceId":"nmt-service"}}',
    )
    call_next = AsyncMock(return_value=Response("ok", status_code=200))
    resp = await middleware.dispatch(request, call_next)

    assert resp.status_code == 503
    middleware._resolve_service.assert_not_called()
    call_next.assert_not_called()


@pytest.mark.asyncio
async def test_health_gate_maps_model_service_id_to_task_microservice_name(middleware):
    # Incoming requests may carry a model-management service id (not the config-service service_name).
    expected_health_service_id = "ocr-service"

    middleware._fetch_health_status = AsyncMock(
        return_value={
            "service_id": expected_health_service_id,
            "state": "unhealthy",
            "last_check": "2026-04-14T00:00:00+00:00",
        }
    )
    middleware._resolve_service = AsyncMock()

    request = _make_request(
        "POST",
        "/api/v1/ocr/inference",
        body=b'{"config":{"serviceId":"ai4bharat/surya-ocr-v1--gpu--t4"}}',
    )
    call_next = AsyncMock(return_value=Response("ok", status_code=200))
    resp = await middleware.dispatch(request, call_next)

    assert resp.status_code == 503
    middleware._fetch_health_status.assert_awaited_once_with(expected_health_service_id)
    middleware._resolve_service.assert_not_called()
    call_next.assert_not_called()

