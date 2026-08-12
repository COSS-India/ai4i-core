import importlib.util
import sys
from unittest.mock import MagicMock
import pytest
from fastapi import Request

_spec = importlib.util.spec_from_file_location(
    "app.routes.telemetry", "app/routes/telemetry.py"
)
telemetry = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.telemetry"] = telemetry
_spec.loader.exec_module(telemetry)


def make_request(headers):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "app": MagicMock(),
    }
    return Request(scope)


def make_client(hits):
    client = MagicMock()
    client.get_trace_by_id.return_value = {"hits": {"hits": hits}}
    return client


@pytest.mark.asyncio
async def test_service_name_comes_from_span_not_hardcoded():
    hits = [
        {"_source": {"@timestamp": "t1", "name": "request", "context": {"trace_id": "0xabc", "parent_span_id": ""},
                     "attributes": {"tenantId": "system"}, "service_name": "ai4x-inference-real"}},
        {"_source": {"@timestamp": "t2", "name": "model", "context": {"trace_id": "0xabc", "parent_span_id": ""},
                     "attributes": {"task_type": "llm"}, "service_name": "ai4x-inference-real"}},
    ]
    req = make_request({"X-Permission-IDS": "1"})
    client = make_client(hits)

    result = await telemetry.get_trace_by_id("0xabc", req, client)

    assert result.service == "ai4x-inference-real"
    assert result.service_version is None


@pytest.mark.asyncio
async def test_service_falls_back_when_no_span_carries_it():
    hits = [
        {"_source": {"@timestamp": "t1", "name": "request", "context": {"trace_id": "0xabc", "parent_span_id": ""},
                     "attributes": {"tenantId": "system"}}},
    ]
    req = make_request({"X-Permission-IDS": "1"})
    client = make_client(hits)

    result = await telemetry.get_trace_by_id("0xabc", req, client)

    assert result.service == "ai4x-inference"
