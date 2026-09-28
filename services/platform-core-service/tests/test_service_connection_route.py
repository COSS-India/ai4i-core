"""End-to-end test for POST /services/test-connection (service-creation "Try it").

Drives the real route -> ServiceService.test_connection -> connection_tester
stack over real HTTP against a throwaway local inference server; only the
model repository and the SSRF DNS check are faked.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils import endpoint_validator as ev

# See test_service_rbac_filtering.py: load service.py by path, since
# app/routes/__init__.py eagerly imports every route module.
if "app.routes.service" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("app.routes.service", "app/routes/service.py")
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["app.routes.service"] = _mod
    _spec.loader.exec_module(_mod)
_route_mod = sys.modules["app.routes.service"]

ServiceService = importlib.import_module("app.services.model-management.service_service").ServiceService


class _Handler(BaseHTTPRequestHandler):
    ROUTES = {
        "/ok": (200, {"output": [{"source": "hi", "target": "नमस्ते"}]}),
        "/bad": (422, {"detail": "sourceLanguage is required"}),
        "/unauth": (401, {"detail": "invalid token"}),
    }

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        code, body = self.ROUTES.get(self.path, (404, {"detail": "Not Found"}))
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


@pytest.fixture(scope="module")
def upstream():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def client(monkeypatch):
    async def _safe(_host, **_kw):
        return True

    monkeypatch.setattr(ev, "is_safe_host", _safe)
    model = SimpleNamespace(
        task={"type": "nmt"},
        inference_endpoint={"schema": {"request": {"input": [{"source": "hi"}]}}},
    )
    svc = ServiceService.__new__(ServiceService)
    svc._models = SimpleNamespace(
        get_by_id_version=AsyncMock(side_effect=lambda mid, _v: model if mid == "m1" else None)
    )
    app = FastAPI()
    app.include_router(_route_mod.router, prefix="/api/v1")
    app.dependency_overrides[_route_mod.get_service_service] = lambda: svc
    return TestClient(app)


def _post(client, **body):
    body = {"modelId": "m1", "modelVersion": "1.0", **body}
    r = client.post("/api/v1/services/test-connection", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    return r.json()["data"]


def test_success(client, upstream):
    d = _post(client, endpoint=upstream + "/ok")
    assert d["success"] is True
    assert d["statusCode"] == 200
    assert d["responseBody"]["output"][0]["target"] == "नमस्ते"


def test_rejected_custom_payload_blames_payload(client, upstream):
    d = _post(client, endpoint=upstream + "/bad", requestPayload='{"input": [{"source": "a"}]}')
    assert (d["success"], d["failureCategory"]) == (False, "PAYLOAD")
    assert "sourceLanguage is required" in d["failureReason"]


def test_rejected_model_payload_blames_model_json(client, upstream):
    d = _post(client, endpoint=upstream + "/bad")
    assert d["failureCategory"] == "MODEL_JSON"


def test_wrong_path_blames_endpoint(client, upstream):
    assert _post(client, endpoint=upstream + "/nope")["failureCategory"] == "ENDPOINT"


def test_unreachable_blames_endpoint(client):
    d = _post(client, endpoint="http://127.0.0.1:1/ok")
    assert d["failureCategory"] == "ENDPOINT"
    assert d["statusCode"] is None


def test_bad_token_blames_auth(client, upstream):
    assert _post(client, endpoint=upstream + "/unauth", authToken="x")["failureCategory"] == "AUTH"


def test_invalid_json_payload(client, upstream):
    d = _post(client, endpoint=upstream + "/ok", requestPayload='{"input": [,]}')
    assert d["failureCategory"] == "PAYLOAD"
    assert "line 1" in d["failureReason"]


def test_unknown_model_blames_model_json(client, upstream):
    d = _post(client, modelId="nope", endpoint=upstream + "/ok")
    assert d["failureCategory"] == "MODEL_JSON"
    assert "not found" in d["failureReason"]


def test_missing_endpoint_is_422(client):
    r = client.post("/api/v1/services/test-connection", json={"modelId": "m1", "modelVersion": "1.0"})
    assert r.status_code == 422
