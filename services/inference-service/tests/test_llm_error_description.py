"""Tests for LLM error description propagation to OTel span status.

The Logs Dashboard ERROR column reads status.description from the OTel
"request" span. NMT/ASR/TTS set this naturally via exception propagation;
LLM returns error status codes without raising, so it must set
_error_description in attrs — consumed by finalize_span — to trigger
StatusCode.ERROR with the right description.
"""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

sys.path.insert(0, ".")

import trace.request_span as request_span_module
from trace.request_span import finalize_span
import routes.inference as inference_routes


def _fake_request() -> SimpleNamespace:
    return SimpleNamespace(
        url=SimpleNamespace(path="/v1/chat/completions"),
        method="POST",
        headers={},
        state=SimpleNamespace(),
    )


@pytest.fixture
def real_tracer():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with patch.object(request_span_module, "tracer", new=provider.get_tracer("test-llm-error-desc")):
        yield provider, exporter


# ── finalize_span: _error_description key behaviour ──────────────────────────

class TestFinalizeSpanErrorDescription:
    def test_sets_error_status_when_error_description_in_attrs(self):
        mock_span = MagicMock()
        attrs = {"_error_description": "upstream returned 502", "status": "failure"}
        finalize_span(mock_span, attrs, ok=True)
        mock_span.set_status.assert_called_once_with(StatusCode.ERROR, "upstream returned 502")

    def test_error_description_not_set_as_span_attribute(self):
        mock_span = MagicMock()
        attrs = {"_error_description": "secret detail", "status": "failure"}
        finalize_span(mock_span, attrs, ok=True)
        for call in mock_span.set_attribute.call_args_list:
            assert call[0][0] != "_error_description"

    def test_ok_set_when_no_error_description(self):
        mock_span = MagicMock()
        finalize_span(mock_span, {"status": "success"}, ok=True)
        mock_span.set_status.assert_called_once_with(StatusCode.OK)

    def test_exception_error_takes_precedence_over_error_description(self):
        mock_span = MagicMock()
        exc = ValueError("direct exception")
        attrs = {"_error_description": "from body", "status": "failure"}
        finalize_span(mock_span, attrs, error=exc)
        args = mock_span.set_status.call_args[0]
        assert args[0] == StatusCode.ERROR
        assert "direct exception" in args[1]

    def test_no_status_set_when_neither_error_nor_ok(self):
        mock_span = MagicMock()
        finalize_span(mock_span, {}, ok=False)
        mock_span.set_status.assert_not_called()


# ── _llm_error_description helper ────────────────────────────────────────────

class TestLlmErrorDescription:
    @pytest.mark.parametrize("body,expected", [
        (
            {"error": {"message": "context length exceeded"}},
            "context length exceeded",
        ),
        (
            {"detail": "No upstream service configured"},
            "No upstream service configured",
        ),
        (
            {"error": {"message": "from error"}, "detail": "from detail"},
            "from error",  # error.message takes precedence over detail
        ),
        ({}, "LLM upstream error 502"),
        ({"error": {}}, "LLM upstream error 502"),  # empty error dict
        ("not a dict", "LLM upstream error 502"),
        (None, "LLM upstream error 502"),
    ])
    def test_extracts_description(self, body, expected):
        from routes.inference import _llm_error_description
        assert _llm_error_description(502, body) == expected

    def test_includes_status_code_in_fallback(self):
        from routes.inference import _llm_error_description
        assert "404" in _llm_error_description(404, {})


# ── Route: _run_llm_chat_consolidated ────────────────────────────────────────

@pytest.mark.asyncio
async def test_consolidated_sets_error_status_on_upstream_error(real_tracer):
    """When the upstream LLM returns 4xx/5xx, the request span must carry
    StatusCode.ERROR + the extracted error description so the Logs Dashboard
    ERROR column is populated — the same behaviour NMT/ASR/TTS get for free
    via exception propagation."""
    _, exporter = real_tracer
    fake_request = _fake_request()

    mock_service = MagicMock()
    mock_service.proxy_traced = AsyncMock(
        return_value=(502, {"error": {"message": "model server crash"}})
    )

    with patch.object(inference_routes, "OpenAIProxyService", return_value=mock_service):
        response = await inference_routes._run_llm_chat_consolidated(
            fake_request, {"model": "svc-1", "messages": []}, path="/v1/chat/completions"
        )

    assert response.status_code == 502
    request_spans = [s for s in exporter.get_finished_spans() if s.name == "request"]
    assert len(request_spans) == 1
    span = request_spans[0]
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == "model server crash"


@pytest.mark.asyncio
async def test_consolidated_no_error_status_on_success(real_tracer):
    """200 responses must not set an error status on the span (regression guard)."""
    _, exporter = real_tracer
    fake_request = _fake_request()

    mock_service = MagicMock()
    mock_service.proxy_traced = AsyncMock(
        return_value=(200, {"choices": [], "model": "gemma", "usage": {}})
    )

    with patch.object(inference_routes, "OpenAIProxyService", return_value=mock_service):
        response = await inference_routes._run_llm_chat_consolidated(
            fake_request, {"model": "svc-1", "messages": []}, path="/v1/chat/completions"
        )

    assert response.status_code == 200
    request_spans = [s for s in exporter.get_finished_spans() if s.name == "request"]
    assert request_spans[0].status.status_code == StatusCode.OK


@pytest.mark.asyncio
async def test_consolidated_uses_detail_field_when_no_error_message(real_tracer):
    """Falls back to body.detail when body has no error.message."""
    _, exporter = real_tracer
    fake_request = _fake_request()

    mock_service = MagicMock()
    mock_service.proxy_traced = AsyncMock(
        return_value=(403, {"detail": "tier quota exceeded"})
    )

    with patch.object(inference_routes, "OpenAIProxyService", return_value=mock_service):
        await inference_routes._run_llm_chat_consolidated(
            fake_request, {"model": "svc-1", "messages": []}, path="/v1/chat/completions"
        )

    request_spans = [s for s in exporter.get_finished_spans() if s.name == "request"]
    span = request_spans[0]
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == "tier quota exceeded"


# ── Route: _run_llm_chat_stream ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_sets_error_status_on_kind_error(real_tracer):
    """The streaming error branch must also populate status.description."""
    _, exporter = real_tracer
    fake_request = _fake_request()

    mock_service = MagicMock()
    mock_service.proxy_traced_stream = AsyncMock(
        return_value=(
            "error", 502, {"error": {"message": "vLLM server crash"}},
            {"service_id": "svc-1", "model_name": "gemma"},
        )
    )

    with patch.object(inference_routes, "OpenAIProxyService", return_value=mock_service):
        response = await inference_routes._run_llm_chat_stream(
            fake_request, {"model": "svc-1", "stream": True}, path="/v1/chat/completions"
        )

    assert response.status_code == 502
    request_spans = [s for s in exporter.get_finished_spans() if s.name == "request"]
    assert len(request_spans) == 1
    span = request_spans[0]
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == "vLLM server crash"


# ── Route: _run_llm_chat tag validation ──────────────────────────────────────

@pytest.mark.asyncio
async def test_tag_validation_error_sets_error_description(real_tracer):
    """A tag-validation 400 must carry the validation message as status.description."""
    _, exporter = real_tracer
    fake_request = _fake_request()
    fake_request.state = SimpleNamespace(service_id="")

    with patch.object(
        inference_routes, "validate_request_tags",
        return_value=("user", "user field must be a non-empty string"),
    ), patch.object(
        inference_routes, "OpenAIProxyService",
        return_value=MagicMock(),
    ):
        response = await inference_routes._run_llm_chat(
            fake_request,
            {"model": "svc-1", "messages": [], "user": 123},
            path="/v1/chat/completions",
        )

    assert response.status_code == 400
    request_spans = [s for s in exporter.get_finished_spans() if s.name == "request"]
    assert len(request_spans) == 1
    span = request_spans[0]
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == "user field must be a non-empty string"
