"""The root "request" span as the source of the request's usage_events row.

The billing consumer writes one usage_events row per API-key request from
this span, and the Usage Dashboard counts requests and failures by its
status_code and groups them by its service_id / task_type. So the span must
carry the service and task on every path, and the HTTP status the client
actually got — not 500 for a 403/404/502.
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, ".")

import trace.request_span as request_span_module
from orchestrator.orchestrator import Orchestrator
from utils.http_status import http_status_for


@pytest.fixture
def exporter():
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    with patch.object(request_span_module, "tracer", new=provider.get_tracer("test-request-span")):
        yield exp


def _request_span(exporter):
    (span,) = [s for s in exporter.get_finished_spans() if s.name == "request"]
    return span.attributes


class TestHttpStatusFor:
    @pytest.mark.parametrize(("exc", "status"), [
        (PermissionError("tier"), 403),
        (ValueError("bad input"), 400),
        (NotImplementedError("pii"), 501),
        (LookupError("no such service"), 404),
        (ConnectionError("triton down"), 502),
        (RuntimeError("upstream 429"), 502),
        (KeyError("bug"), 500),          # a LookupError subclass, but a programming error
        (Exception("boom"), 500),
    ])
    def test_status(self, exc, status):
        assert http_status_for(exc) == status

    def test_walks_the_cause_chain(self):
        try:
            try:
                raise LookupError("unknown serviceId")
            except LookupError as inner:
                raise RuntimeError("resolution failed") from inner
        except RuntimeError as exc:
            assert http_status_for(exc) == 404


class TestTracedSpanStatusFor:
    def test_status_for_overrides_the_default(self, exporter):
        with pytest.raises(PermissionError):
            with request_span_module.traced_span("request", root=True, classify_status=True,
                                                 status_for=http_status_for):
                raise PermissionError("not on your tier")
        assert (_request_span(exporter)["status"], _request_span(exporter)["status_code"]) == ("failure", 403)

    def test_default_is_unchanged(self, exporter):
        with pytest.raises(PermissionError):
            with request_span_module.traced_span("request", root=True, classify_status=True):
                raise PermissionError("not on your tier")
        assert _request_span(exporter)["status_code"] == 500


def _orchestrator() -> Orchestrator:
    with patch("orchestrator.orchestrator.InferenceServerResolver"):
        return Orchestrator()


def _http_request(path="/api/v1/nmt/inference"):
    request = MagicMock()
    request.url.path = path
    request.method = "POST"
    request.headers = {}
    return request


@pytest.mark.asyncio
class TestTritonRequestSpan:
    async def test_failure_carries_service_task_and_http_status(self, exporter):
        orch = _orchestrator()
        # As the resolver raises it: LookupError wrapped in RuntimeError (→ 404).
        resolution_error = RuntimeError("resolution failed")
        resolution_error.__cause__ = LookupError("unknown serviceId")
        orch._resolve_service_and_model = AsyncMock(side_effect=resolution_error)

        payload = {"task_type": "NMT", "config": {"serviceId": "svc-typo"}, "input": [{"source": "hi"}]}
        with pytest.raises(RuntimeError):
            await orch.route_inference(payload=payload, request=_http_request())

        attrs = _request_span(exporter)
        assert (attrs["status_code"], attrs["service_id"], attrs["task_type"]) == (404, "svc-typo", "nmt")
        assert attrs["url"] == "/api/v1/nmt/inference"

    async def test_success_carries_the_resolved_service(self, exporter):
        orch = _orchestrator()
        orch._resolve_service_and_model = AsyncMock(return_value={"serviceId": "svc-resolved"})
        task_service = MagicMock()
        task_service.process = AsyncMock(return_value={"output": []})
        orch._get_task_service = MagicMock(return_value=task_service)

        await orch.route_inference(payload={"task_type": "NMT", "input": []}, request=_http_request())

        attrs = _request_span(exporter)
        assert (attrs["status_code"], attrs["service_id"], attrs["task_type"]) == (200, "svc-resolved", "nmt")


class TestRejectedRequestSpan:
    """A body that fails validation never reaches the route; the validation
    handler (app_factory) calls record_rejected_request so the request is
    still one failed row."""

    def test_emits_a_failed_request_span(self, exporter):
        request_span_module.record_rejected_request(_http_request(), 400)

        attrs = _request_span(exporter)
        assert (attrs["status"], attrs["status_code"], attrs["url"]) == ("failure", 400, "/api/v1/nmt/inference")

    def test_propagates_description_to_span_status(self, exporter):
        request_span_module.record_rejected_request(_http_request(), 400, "field required")

        (span,) = [s for s in exporter.get_finished_spans() if s.name == "request"]
        assert span.status.description == "field required"
