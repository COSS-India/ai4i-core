"""Coverage for request propagation into LLM proxy and tracing header reader."""

import importlib.util
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from starlette.requests import Request

from ai4i_core.observability.payload_analysis import analyze_payload
from ai4i_core.observability.tracing_headers import inject_tracing_headers
from trace.tracing_headers import TRACING_HEADER_PREFIX, get_tracing_attributes

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_LLM_SERVICE_PATH = _ROOT / "services" / "llm_service.py"
_LLM_SPEC = importlib.util.spec_from_file_location("llm_service_under_test", _LLM_SERVICE_PATH)
_LLM_MODULE = importlib.util.module_from_spec(_LLM_SPEC)
assert _LLM_SPEC.loader is not None
_LLM_SPEC.loader.exec_module(_LLM_MODULE)
OpenAIProxyService = _LLM_MODULE.OpenAIProxyService


@pytest.fixture(autouse=True)
def _otel_tracer():
    provider = TracerProvider()
    with patch("trace.request_span.tracer", provider.get_tracer("test")):
        with patch("trace.request_span.log_span_attributes"):
            yield


def _request_with_analysis(payload: dict) -> Request:
    analysis = analyze_payload(payload)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat/completions",
        "headers": [],
    }
    inject_tracing_headers(scope, analysis)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


class TestTracingHeadersInferenceModule:
    def test_returns_empty_for_none_request(self):
        assert get_tracing_attributes(None) == {}

    def test_reexports_prefix(self):
        assert TRACING_HEADER_PREFIX == "X-Tracing-"


class TestLlmProxyTracedRequestWiring:
    @pytest.mark.asyncio
    async def test_proxy_traced_reads_tracing_headers_from_request(self):
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello there"}],
            "serviceId": "llm-svc-1",
        }
        request = _request_with_analysis(payload)
        service = OpenAIProxyService()

        with patch.object(
            service,
            "proxy",
            new=AsyncMock(
                return_value=(
                    200,
                    {
                        "model": "test-model",
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                    },
                )
            ),
        ):
            status, body = await service.proxy_traced(
                path="/v1/chat/completions",
                payload=dict(payload),
                request=request,
            )

        assert status == 200
        assert body["usage"]["prompt_tokens"] == 4

    @pytest.mark.asyncio
    async def test_proxy_traced_without_request_still_works(self):
        payload = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
        service = OpenAIProxyService()

        with patch.object(
            service,
            "proxy",
            new=AsyncMock(return_value=(200, {"usage": {"prompt_tokens": 1, "completion_tokens": 1}})),
        ):
            status, _ = await service.proxy_traced(
                path="/v1/chat/completions",
                payload=payload,
            )

        assert status == 200

    @pytest.mark.asyncio
    async def test_proxy_traced_strips_service_id_from_payload(self):
        payload = {"model": "m", "serviceId": "to-strip", "messages": []}
        service = OpenAIProxyService()
        captured = {}

        async def _capture_proxy(path, payload):
            captured["payload"] = payload
            return 200, {"usage": {}}

        with patch.object(service, "proxy", new=AsyncMock(side_effect=_capture_proxy)):
            await service.proxy_traced(path="/v1/chat", payload=payload)

        assert "serviceId" not in captured["payload"]
