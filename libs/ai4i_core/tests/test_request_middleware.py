"""Unit tests: RequestMiddleware's per-request log line.

Covers:
  - service_id/model_id are read off request.state (same pattern
    ObservabilityMiddleware already uses for Prometheus) and land on the
    logged context.
  - auth_type (X-Auth-Type) and application_id (X-Application-ID) are read
    off request headers and land on the logged context.
  - fields are simply omitted, not logged as empty strings, when unset.
  - 4xx responses are logged (no longer skipped).
"""
from unittest.mock import patch

from fastapi import FastAPI, Request, Response
from starlette.testclient import TestClient

from ai4i_core.logging.middleware import RequestMiddleware


def _app_with_middleware(state_setter=None, status_code=200):
    app = FastAPI()
    app.add_middleware(RequestMiddleware)

    @app.post("/api/v1/nmt/inference")
    async def handler(request: Request):
        if state_setter:
            state_setter(request)
        return Response(status_code=status_code, content=b"{}", media_type="application/json")

    return app


def _dispatch_and_get_ctx(app, headers=None):
    with patch("ai4i_core.logging.middleware.logger") as mock_logger:
        TestClient(app).post("/api/v1/nmt/inference", headers=headers or {})
        call = mock_logger.info.call_args or mock_logger.error.call_args
        assert call is not None, "expected RequestMiddleware to log the request"
        return call.kwargs["extra"]["context"]


class TestServiceAndModelId:
    def test_reads_service_id_and_model_id_from_request_state(self):
        def setter(request):
            request.state.service_id = "svc-nmt-en-hi"
            request.state.model_id = "hash-model-1"

        ctx = _dispatch_and_get_ctx(_app_with_middleware(setter))
        assert ctx["service_id"] == "svc-nmt-en-hi"
        assert ctx["model_id"] == "hash-model-1"

    def test_omits_service_id_and_model_id_when_unset(self):
        ctx = _dispatch_and_get_ctx(_app_with_middleware())
        assert "service_id" not in ctx
        assert "model_id" not in ctx


class TestAuthType:
    def test_reads_auth_type_from_header(self):
        ctx = _dispatch_and_get_ctx(_app_with_middleware(), headers={"X-Auth-Type": "api_key"})
        assert ctx["auth_type"] == "api_key"

    def test_omits_auth_type_when_header_absent(self):
        ctx = _dispatch_and_get_ctx(_app_with_middleware())
        assert "auth_type" not in ctx


class TestApplicationId:
    def test_reads_application_id_from_header(self):
        ctx = _dispatch_and_get_ctx(
            _app_with_middleware(), headers={"X-Application-ID": "app-42"}
        )
        assert ctx["application_id"] == "app-42"

    def test_omits_application_id_when_header_absent(self):
        ctx = _dispatch_and_get_ctx(_app_with_middleware())
        assert "application_id" not in ctx


class TestFourXXNoLongerSkipped:
    def test_4xx_response_is_logged(self):
        ctx = _dispatch_and_get_ctx(_app_with_middleware(status_code=422))
        assert ctx["status_code"] == 422

    def test_5xx_still_logged_at_error_level(self):
        with patch("ai4i_core.logging.middleware.logger") as mock_logger:
            TestClient(_app_with_middleware(status_code=500)).post("/api/v1/nmt/inference")
            assert mock_logger.error.called
            assert not mock_logger.info.called
