"""
Unit tests for the platform management response format — platform-core-service.

Tests:
  - platform_success_response / platform_error_response helpers
  - PlatformResponseMiddleware (path matching, requestId injection, error transform)
  - Model route response shape
  - Service route response shape
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse


# ---------------------------------------------------------------------------
# Shared response helpers (same functions as auth-service — imported from lib)
# ---------------------------------------------------------------------------

class TestPlatformSuccessResponse:
    def test_basic_shape(self):
        from app.core.responses import platform_success_response
        resp = platform_success_response(data={"modelId": "m1"})

        assert resp["status"] == "OK"
        assert resp["statusCode"] == 200
        assert resp["message"] == ""
        assert resp["data"] == {"modelId": "m1"}
        assert resp["requestId"].startswith("req_")
        assert "success" not in resp
        assert "meta" not in resp          # old meta field must be absent
        assert "error" not in resp

    def test_message_field_carries_operation_result(self):
        from app.core.responses import platform_success_response
        resp = platform_success_response(
            data={"modelId": "m1"},
            message="Model 'whisper' created successfully."
        )
        assert resp["message"] == "Model 'whisper' created successfully."

    def test_status_code_201_for_creates(self):
        from app.core.responses import platform_success_response
        resp = platform_success_response(data={}, status_code=201)
        assert resp["statusCode"] == 201

    def test_request_id_propagated(self):
        from app.core.responses import platform_success_response
        resp = platform_success_response(data={}, request_id="req_test123")
        assert resp["requestId"] == "req_test123"


class TestPlatformErrorResponse:
    def test_basic_shape(self):
        from app.core.responses import platform_error_response
        resp = platform_error_response(
            http_status=422,
            message="Validation failed",
            error_code="VALIDATION_ERROR",
        )

        assert resp["status"] == "ERROR"
        assert resp["statusCode"] == 422
        assert resp["message"] == "Validation failed"
        assert resp["error"]["code"] == 422
        assert resp["error"]["message"] == "VALIDATION_ERROR"
        assert "VALIDATION_ERROR" in resp["error"]["params"]
        assert "success" not in resp
        assert "data" not in resp

    def test_params_default_to_code_message_pair(self):
        from app.core.responses import platform_error_response
        resp = platform_error_response(404, "Not found", "NOT_FOUND")
        assert resp["error"]["params"] == {"NOT_FOUND": "Not found"}

    def test_custom_params_override_default(self):
        from app.core.responses import platform_error_response
        custom = {"INVALID_DATA": "Missing required field 'name'"}
        resp = platform_error_response(400, "Bad request", "INVALID_DATA", params=custom)
        assert resp["error"]["params"] == custom


# ---------------------------------------------------------------------------
# PlatformResponseMiddleware — path matching
# ---------------------------------------------------------------------------

class TestPlatformResponseMiddlewarePathMatching:
    def test_managed_paths_activate_middleware(self):
        from app.middleware.platform_response import _is_managed
        assert _is_managed("/models")
        assert _is_managed("/api/v1/models")
        assert _is_managed("/models/some-hash-id")
        assert _is_managed("/services")
        assert _is_managed("/api/v1/services")
        assert _is_managed("/services/try-it-service-list")
        assert _is_managed("/api/v1/services/some-id")

    def test_non_managed_paths_bypass_middleware(self):
        from app.middleware.platform_response import _is_managed
        assert not _is_managed("/health")
        assert not _is_managed("/ready")
        assert not _is_managed("/docs")
        assert not _is_managed("/openapi.json")

    def test_middleware_injects_request_id_in_state(self):
        from app.middleware.platform_response import PlatformResponseMiddleware

        app = FastAPI()
        app.add_middleware(PlatformResponseMiddleware)
        captured = {}

        @app.get("/models")
        async def endpoint(request):
            captured["rid"] = getattr(request.state, "platform_request_id", None)
            return {"ok": True}

        with TestClient(app, raise_server_exceptions=True) as client:
            client.get("/models")

        assert captured["rid"] is not None
        assert captured["rid"].startswith("req_")

    def test_non_managed_path_has_no_request_id(self):
        from app.middleware.platform_response import PlatformResponseMiddleware

        app = FastAPI()
        app.add_middleware(PlatformResponseMiddleware)
        captured = {}

        @app.get("/health")
        async def endpoint(request):
            captured["rid"] = getattr(request.state, "platform_request_id", "NOT_SET")
            return {"status": "ok"}

        with TestClient(app) as client:
            client.get("/health")

        assert captured["rid"] == "NOT_SET"


# ---------------------------------------------------------------------------
# PlatformResponseMiddleware — error transformation
# ---------------------------------------------------------------------------

class TestPlatformResponseMiddlewareErrorTransform:
    def _make_error_app(self, path: str, status_code: int, detail):
        from app.middleware.platform_response import PlatformResponseMiddleware

        app = FastAPI()
        app.add_middleware(PlatformResponseMiddleware)

        @app.get(path)
        async def endpoint():
            raise RuntimeError("intentional")

        @app.exception_handler(RuntimeError)
        async def handler(request, exc):
            return JSONResponse(status_code=status_code, content={"detail": detail})

        return app

    def test_model_404_is_transformed(self):
        app = self._make_error_app(
            "/models",
            404,
            {"code": "MODEL_NOT_FOUND", "message": "Model not found."},
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/models")

        body = resp.json()
        assert resp.status_code == 404
        assert body["status"] == "ERROR"
        assert body["statusCode"] == 404
        assert body["message"] == "Model not found."
        assert body["error"]["message"] == "MODEL_NOT_FOUND"
        assert body["error"]["code"] == 404
        assert body["requestId"].startswith("req_")

    def test_service_422_validation_error_is_transformed(self):
        app = self._make_error_app(
            "/services",
            422,
            [{"loc": ["body", "name"], "msg": "field required", "type": "value_error.missing"}],
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/services")

        body = resp.json()
        assert body["status"] == "ERROR"
        assert body["statusCode"] == 422
        assert body["error"]["message"] == "VALIDATION_ERROR"
        assert body["message"] == "field required"

    def test_success_2xx_bypasses_transformation(self):
        from app.middleware.platform_response import PlatformResponseMiddleware

        app = FastAPI()
        app.add_middleware(PlatformResponseMiddleware)

        @app.get("/models")
        async def endpoint():
            return {
                "requestId": "req_predefined",
                "status": "OK",
                "statusCode": 200,
                "message": "",
                "data": [],
            }

        with TestClient(app) as client:
            resp = client.get("/models")

        body = resp.json()
        assert body["requestId"] == "req_predefined"
        assert body["status"] == "OK"
        assert "error" not in body

    def test_request_id_consistent(self):
        """requestId in request.state matches the one in the error response."""
        from app.middleware.platform_response import PlatformResponseMiddleware

        app = FastAPI()
        app.add_middleware(PlatformResponseMiddleware)
        captured_rid = {}

        @app.get("/models")
        async def endpoint(request):
            captured_rid["rid"] = getattr(request.state, "platform_request_id", None)
            raise RuntimeError("force error")

        @app.exception_handler(RuntimeError)
        async def handler(request, exc):
            return JSONResponse(
                status_code=500,
                content={"detail": {"code": "INTERNAL_ERROR", "message": "Internal error"}},
            )

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/models")

        body = resp.json()
        assert body["requestId"] == captured_rid["rid"]


# ---------------------------------------------------------------------------
# Regression: old success_response format still works for other uses
# ---------------------------------------------------------------------------

class TestOldFormatNotBroken:
    def test_success_response_still_has_success_true(self):
        from app.core.responses import success_response
        resp = success_response(data={"x": 1})
        assert resp["success"] is True
        assert resp["data"]["x"] == 1
        assert "requestId" not in resp

    def test_error_response_still_has_success_false(self):
        from app.core.responses import error_response
        resp = error_response("NOT_FOUND", "Not found")
        assert resp["success"] is False
        assert resp["error"]["code"] == "NOT_FOUND"
        assert "requestId" not in resp
