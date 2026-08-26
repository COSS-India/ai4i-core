"""Unit tests: the streaming LLM chat route bridges usage/labels onto
request.state on BOTH the success and error paths.

Regression: the "kind == error" branch in _run_llm_chat_stream returned a
JSONResponse without ever calling _bridge_llm_usage_to_request(), so a
failed streaming request carried no model_id — model_breakdown drops the
empty-model_id bucket entirely, so the failure silently vanished from the
model's totals instead of counting against its success_pct.
"""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, ".")

from ai4i_core.context import set_llm_usage_model_id

import routes.inference as inference_routes
import services.llm_service as llm_service_module
import trace.request_span as request_span_module


def _fake_request() -> SimpleNamespace:
    return SimpleNamespace(
        url=SimpleNamespace(path="/v1/chat/completions"),
        method="POST",
        headers={},
        state=SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_error_branch_bridges_model_id_onto_request_state():
    # Simulates what _prepare_request() would have set before the failure
    # occurred (e.g. MMS resolved the service, then the upstream connection
    # itself failed) — proxy_traced_stream is mocked out entirely below, so
    # this stands in for that earlier step.
    set_llm_usage_model_id("hash-gemma-v1")
    fake_request = _fake_request()

    mock_service = MagicMock()
    mock_service.proxy_traced_stream = AsyncMock(
        return_value=(
            "error", 502, {"detail": "Upstream LLM request failed"},
            {"service_id": "svc-1", "model_name": "google/gemma-4-E4B-it"},
        )
    )

    with patch.object(inference_routes, "OpenAIProxyService", return_value=mock_service):
        response = await inference_routes._run_llm_chat_stream(
            fake_request, {"model": "svc-1"}, path="/v1/chat/completions",
        )

    assert response.status_code == 502
    assert fake_request.state.model_id == "hash-gemma-v1"

    set_llm_usage_model_id(None)


@pytest.mark.asyncio
async def test_error_branch_defaults_model_id_to_empty_string_when_unresolved():
    """Resolution itself failed before any model_id was ever known — the
    bridge must still run (and land "" rather than leaving the attribute
    unset), not skip labeling entirely."""
    set_llm_usage_model_id(None)
    fake_request = _fake_request()

    mock_service = MagicMock()
    mock_service.proxy_traced_stream = AsyncMock(
        return_value=(
            "error", 404, {"detail": "Service 'svc-1' not found"},
            {"service_id": "svc-1", "model_name": ""},
        )
    )

    with patch.object(inference_routes, "OpenAIProxyService", return_value=mock_service):
        response = await inference_routes._run_llm_chat_stream(
            fake_request, {"model": "svc-1"}, path="/v1/chat/completions",
        )

    assert response.status_code == 404
    assert fake_request.state.model_id == ""


# ── regression: streaming rejection's "model" span must nest under "request" ─

@pytest.mark.asyncio
async def test_error_branch_model_span_is_a_child_of_request_span():
    """
    Regression test for the split-trace-tree bug: proxy_traced_stream() used
    to open its own "model" span for a rejection BEFORE _run_llm_chat_stream
    ever opened its "request" span, so "model" exported with no parent and a
    different otel_trace_id than "request" — two disconnected roots for one
    logical request. Fixed by having proxy_traced_stream() return
    (kind, status_code, body, model_ctx) instead of opening the span itself,
    so the route builds "model" from inside its already-open "request" span.

    Uses a real TracerProvider + InMemorySpanExporter (unlike the other
    tests here, which mock OpenAIProxyService entirely) specifically to
    inspect real parent/trace_id linkage — attribute values alone can't
    prove the spans are actually nested.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    real_tracer = provider.get_tracer("test-llm-chat-stream-bridge")

    fake_request = _fake_request()

    with patch.object(request_span_module, "tracer", new=real_tracer), \
         patch.object(
             llm_service_module.OpenAIProxyService, "resolve_upstream_url",
             new=AsyncMock(side_effect=LookupError("not found")),
         ):
        response = await inference_routes._run_llm_chat_stream(
            fake_request, {"model": "missing-svc", "stream": True},
            path="/v1/chat/completions",
        )

    assert response.status_code == 404

    spans = exporter.get_finished_spans()
    request_spans = [s for s in spans if s.name == "request"]
    model_spans = [s for s in spans if s.name == "model"]
    assert len(request_spans) == 1, f"expected exactly one 'request' span, got {len(request_spans)}"
    assert len(model_spans) == 1, f"expected exactly one 'model' span, got {len(model_spans)}"
    request_span, model_span = request_spans[0], model_spans[0]

    # The actual regression: "model" must be a child of "request", not an
    # unrelated root. A parent-less/foreign-trace span would fail both of
    # these before the fix.
    assert model_span.parent is not None, "model span exported with no parent at all"
    assert model_span.parent.span_id == request_span.context.span_id
    assert model_span.context.trace_id == request_span.context.trace_id

    assert model_span.attributes.get("task_type") == "LLM"
    assert model_span.attributes.get("service_id") == "missing-svc"
    assert model_span.attributes.get("status") == "failure"
    assert model_span.attributes.get("status_code") == 404
