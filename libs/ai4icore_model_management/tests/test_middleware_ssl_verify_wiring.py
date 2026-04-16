from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.responses import Response

from ai4icore_model_management.client import ModelManagementClient, ServiceInfo
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


@pytest.mark.asyncio
async def test_dispatch_wires_ssl_verify_into_request_state_and_triton_client(monkeypatch):
    # Ensure the B1 fix is exercised end-to-end through dispatch(), not just in resolver helpers.
    mock_client = MagicMock(spec=ModelManagementClient)
    mock_client.select_experiment_variant = AsyncMock(return_value=None)

    app = MagicMock()
    middleware = ModelResolutionMiddleware(
        app,
        model_management_client=mock_client,
        redis_client=None,
        cache_ttl_seconds=300,
        default_triton_endpoint=None,
        default_triton_api_key="default-key",
        enabled_paths=["/api/v1"],
        config_service_url="",
        health_gate_enabled=False,
    )

    service_id = "asr-service"
    service_info = ServiceInfo(
        service_id=service_id,
        model_id="model-1",
        endpoint="http://example.com:8000",
        is_published=True,
        ssl_verify=False,
    )
    middleware._get_service_info = AsyncMock(return_value=service_info)
    middleware._get_service_registry_entry = AsyncMock(return_value=("http://example.com:8000", "test-model"))

    captured = {}

    class _FakeTritonClient:
        def __init__(self, triton_url, api_key=None, ssl_verify=None):
            captured["triton_url"] = triton_url
            captured["api_key"] = api_key
            captured["ssl_verify"] = ssl_verify

    monkeypatch.setattr(
        "ai4icore_model_management.middleware.TritonClient",
        _FakeTritonClient,
        raising=True,
    )

    request = _make_request(
        "POST",
        "/api/v1/asr/inference",
        body=b'{"config":{"serviceId":"asr-service"}}',
    )
    call_next = AsyncMock(return_value=Response("ok", status_code=200))
    resp = await middleware.dispatch(request, call_next)

    assert resp.status_code == 200
    assert request.state.ssl_verify is False
    assert captured["ssl_verify"] is False

