"""One billable ai-inference span per request, whatever the call mode.

The PPU consumer bills ai-inference spans and writes one usage_events row per
span, keyed (correlation_id, occurred_at) since migration a7c3e9f1b5d2 dropped
span_id. A per_item request (TTS chunks, per-item audio) calls Triton once per
item: those calls must be ai-inference-call children, with the request's
units summed on the single ai-inference span — otherwise a chunked request is
billed and recorded once per chunk.
"""
import sys
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, ".")

import trace.request_span as request_span_module
import trace.span_attributes as span_attributes_module
from services.base.task_service import BaseTaskService

SERVICE_INFO = {"name": "tts-model", "endpoint": "triton:8001", "serviceId": "svc-tts"}


class _FakeTaskService(BaseTaskService):
    """Echoes each item's source back; fails on the item named in fail_on."""

    payload_key = "input"
    TRITON_CALL_MODE = "per_item"

    def __init__(self, fail_on=None):
        super().__init__()
        self.fail_on = fail_on
        self.calls = 0

    async def convert_payload_to_triton_format(self, items, config):
        return items, None

    async def _call_triton_inference(self, triton_endpoint, triton_inputs, triton_outputs, api_key=None):
        self.calls += 1
        if any(item["source"] == self.fail_on for item in triton_inputs):
            raise RuntimeError("triton call failed")
        return triton_inputs

    async def convert_triton_output_to_task_format(self, raw):
        return [{"target": item["source"]} for item in raw]


@pytest.fixture
def exporter():
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))

    async def _characters(_task_type):
        return "characters"

    with patch.object(request_span_module, "tracer", new=provider.get_tracer("test-span-per-request")), \
            patch.object(span_attributes_module, "get_unit_type", new=_characters):
        yield exp


def _spans(exporter, name):
    return [s for s in exporter.get_finished_spans() if s.name == name]


def _payload(*sources):
    return {"task_type": "TTS", "input": [{"source": s} for s in sources], "config": {}}


@pytest.mark.asyncio
async def test_per_item_request_is_one_billable_span_with_summed_units(exporter):
    service = _FakeTaskService()
    await service.run_inference(_payload("abc", "defgh", "ij"), SERVICE_INFO)

    assert service.calls == 3
    (billable,) = _spans(exporter, "ai-inference")
    assert billable.attributes["input_tokens"] == 10          # 3 + 5 + 2 characters
    assert billable.attributes["service_id"] == "svc-tts"
    assert service.billed_input == 10

    calls = _spans(exporter, "ai-inference-call")
    assert [c.attributes["input_tokens"] for c in calls] == [3, 5, 2]
    assert all(c.parent.span_id == billable.context.span_id for c in calls)


@pytest.mark.asyncio
async def test_single_call_request_adds_no_child_span(exporter):
    """Batch mode (or a one-item per_item request) is one call: the parent
    span already times it, so the trace keeps its usual spans."""
    service = _FakeTaskService()
    with patch.object(_FakeTaskService, "TRITON_CALL_MODE", "batch"):
        await service.run_inference(_payload("abc", "de"), SERVICE_INFO)
    await service.run_inference(_payload("abc"), SERVICE_INFO)   # per_item, one item

    assert [s.attributes["input_tokens"] for s in _spans(exporter, "ai-inference")] == [5, 3]
    assert _spans(exporter, "ai-inference-call") == []


@pytest.mark.asyncio
async def test_a_failed_call_leaves_the_request_unbilled(exporter):
    """The request fails as a whole, so its span carries zero units — not
    the chunks that happened to succeed before the failing one."""
    service = _FakeTaskService(fail_on="defgh")
    with pytest.raises(RuntimeError):
        await service.run_inference(_payload("abc", "defgh", "ij"), SERVICE_INFO)

    (billable,) = _spans(exporter, "ai-inference")
    assert billable.attributes["input_tokens"] == 0
    assert billable.attributes["status"] == "failure"
    assert [c.attributes["status"] for c in _spans(exporter, "ai-inference-call")] == ["success", "failure"]
