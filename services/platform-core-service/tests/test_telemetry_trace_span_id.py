"""GET /telemetry/traces/{id} returns each span's context.span_id, so a trace
with two "model" / two "ai-inference" spans (a service fallback) still has
distinguishable rows."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

_TELEMETRY_ROUTE_PATH = Path(__file__).resolve().parents[1] / "app" / "routes" / "telemetry.py"
_spec = importlib.util.spec_from_file_location("app.routes.telemetry", _TELEMETRY_ROUTE_PATH)
_telemetry = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.telemetry"] = _telemetry
_spec.loader.exec_module(_telemetry)

TRACE = "305966eb0bfc463787d2e30dac317e79"


def _hit(name: str, span_id: str, service_id: str) -> dict:
    return {
        "_source": {
            "@timestamp": "2026-10-27T16:20:18.000Z",
            "name": name,
            "kind": "SpanKind.INTERNAL",
            "context": {"trace_id": TRACE, "span_id": span_id, "parent_span_id": None},
            "attributes": {"service_id": service_id, "tenantId": "1", "status": "success", "status_code": 200},
            "service_name": "inference-service",
        }
    }


def test_trace_detail_requests_and_returns_span_ids():
    client = MagicMock()
    client.get_trace_by_id.return_value = {"hits": {"hits": [
        _hit("request", "0x01", "fallback-e2e/llm-fallback"),
        _hit("model", "0x02", "fallback-e2e/llm-primary-dead"),
        _hit("model", "0x03", "fallback-e2e/llm-fallback"),
        _hit("ai-inference", "0x04", "fallback-e2e/llm-primary-dead"),
        _hit("ai-inference", "0x05", "fallback-e2e/llm-fallback"),
    ]}}
    request = MagicMock()
    request.headers = {"X-Permission-IDS": "1", "X-Tenant-Id": "1"}

    response = asyncio.run(_telemetry.get_trace_by_id(TRACE, request, opensearch_client=client))

    assert "context.span_id" in client.get_trace_by_id.call_args.kwargs["source_fields"]
    spans = response["spans"] if isinstance(response, dict) else response.spans
    span_ids = [(s["context"] if isinstance(s, dict) else s.context.model_dump())["span_id"] for s in spans]
    assert len(span_ids) == 5 and len(set(span_ids)) == 5


def test_trace_with_no_service_name_returns_200_with_null_service():
    """No span in the trace carries service_name (e.g. an old/edge-case
    emitter) - TraceResponse.service is Optional[str], so this must come back
    as a 200 with service: null, not a 500 from pydantic validation rejecting
    a required field that was never populated."""
    client = MagicMock()
    client.get_trace_by_id.return_value = {"hits": {"hits": [{
        "_source": {
            "@timestamp": "2026-10-27T16:20:18.000Z",
            "name": "request",
            "kind": "SpanKind.INTERNAL",
            "context": {"trace_id": TRACE, "span_id": "0x01", "parent_span_id": None},
            "attributes": {"tenantId": "1", "status": "success", "status_code": 200},
        }
    }]}}

    app = FastAPI()
    app.include_router(_telemetry.router)
    app.dependency_overrides[_telemetry._get_opensearch_client] = lambda: client
    http_client = TestClient(app)

    response = http_client.get(
        f"/telemetry/traces/{TRACE}",
        headers={"X-Permission-IDS": "1", "X-Tenant-Id": "1"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["service"] is None
