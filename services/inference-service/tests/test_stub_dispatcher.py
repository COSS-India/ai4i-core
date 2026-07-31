"""Unit tests for the load-test stub dispatcher.

Covers the TRITON_STUB_MODE gate, the size buckets, the KServe v2 shape of
every fixture, and the fact that GenericTritonMapper (the real converter used
by BaseTaskService.convert_triton_output_to_task_format) consumes them.
"""

import math

import pytest

from config import settings
from orchestrator.task_service_registry import TASK_SERVICE_REGISTRY
from response_test.base_response_test import SMALL_THRESHOLD, MEDIUM_THRESHOLD
from response_test.stub_dispatcher import (
    _STUBS,
    get_llm_stub_response,
    get_stub_response,
)
from services.base.config_mapper import GenericTritonMapper


@pytest.fixture
def stub_mode(monkeypatch):
    """Turn stub mode on for the duration of a test."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", True)


def _text_inputs(length):
    return [{"name": "INPUT_TEXT", "data": ["x" * length]}]


# ── the gate ──────────────────────────────────────────────────────────────────

def test_both_entry_points_return_none_when_mode_is_off(monkeypatch):
    """With the flag off nothing is stubbed, so every caller hits the real path."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)

    assert get_stub_response("NMTTaskService", _text_inputs(10)) is None
    assert get_llm_stub_response({"messages": [{"role": "user", "content": "hi"}]}) is None


def test_unregistered_service_returns_none_even_when_mode_is_on(stub_mode):
    """PII has no stub and must fall through to its real not-implemented path."""
    assert get_stub_response("PIITaskService", _text_inputs(10)) is None


# ── size buckets ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("task_name", sorted(_STUBS))
def test_each_service_has_three_distinct_size_buckets(task_name, stub_mode):
    """Small / medium / large must be distinguishable, or the buckets are pointless."""
    small = get_stub_response(task_name, _text_inputs(SMALL_THRESHOLD - 1))
    medium = get_stub_response(task_name, _text_inputs(SMALL_THRESHOLD))
    large = get_stub_response(task_name, _text_inputs(MEDIUM_THRESHOLD))

    assert small != medium
    assert medium != large


def test_binary_tensor_is_sized_by_byte_length(stub_mode):
    """ASR audio arrives as raw bytes under '_raw', not as a data list."""
    small = get_stub_response("ASRTaskService", [{"name": "AUDIO", "_raw": b"x" * 10}])
    large = get_stub_response("ASRTaskService", [{"name": "AUDIO", "_raw": b"x" * 5000}])

    assert small != large


def test_numeric_data_is_sized_by_element_count(stub_mode):
    """Audio sample lists size off len(), not the stringified elements."""
    small = get_stub_response("ASRTaskService", [{"name": "AUDIO", "data": [0.1] * 10}])
    large = get_stub_response("ASRTaskService", [{"name": "AUDIO", "data": [0.1] * 5000}])

    assert small != large


def test_returns_a_deep_copy(stub_mode):
    """A caller mutating the result must not corrupt the shared constants."""
    first = get_stub_response("NMTTaskService", _text_inputs(10))
    first["outputs"][0]["data"][0] = "mutated"
    second = get_stub_response("NMTTaskService", _text_inputs(10))

    assert second["outputs"][0]["data"][0] != "mutated"


# ── fixture shape ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("task_name", sorted(_STUBS))
def test_stub_is_a_wellformed_kserve_v2_response(task_name, stub_mode):
    """Every fixture must look like what Triton's KServe v2 endpoint returns."""
    for length in (SMALL_THRESHOLD - 1, SMALL_THRESHOLD, MEDIUM_THRESHOLD):
        stub = get_stub_response(task_name, _text_inputs(length))

        assert stub["outputs"], f"{task_name}: no outputs"
        for out in stub["outputs"]:
            assert out["name"]
            assert out["datatype"]
            assert out["shape"]
            assert math.prod(out["shape"]) == len(out["data"]), (
                f"{task_name}/{out['name']}: shape {out['shape']} does not match "
                f"{len(out['data'])} data elements"
            )


@pytest.mark.parametrize("task_name", sorted(_STUBS))
def test_generic_triton_mapper_consumes_the_stub(task_name, stub_mode):
    """The real converter must map every tensor the stub emits.

    adapter_config is per-service data held in MMS, not in this repo, so the
    config here is derived from the stub's own tensor names. That is enough to
    prove the fixture is consumable by GenericTritonMapper and that map_outputs
    finds every tensor it declares.
    """
    stub = get_stub_response(task_name, _text_inputs(10))
    adapter_config = {
        "version": "1.0",
        "inputs": [
            {"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1],
             "value_path": "input.source"},
        ],
        "outputs": [
            {"tensor": out["name"], "dtype": out["datatype"],
             "maps_to": out["name"].lower()}
            for out in stub["outputs"]
        ],
    }

    mapper = GenericTritonMapper(adapter_config)
    items = mapper.to_output_items(mapper.map_outputs(stub))

    assert items
    for out in stub["outputs"]:
        assert out["name"].lower() in items[0]


def test_every_registered_task_service_has_a_stub_except_pii():
    """A new task service without a stub would silently call real Triton."""
    registered = {
        cls.__name__ for cls in TASK_SERVICE_REGISTRY.values()
    } - {"PIITaskService"}

    assert registered == set(_STUBS), (
        f"missing stubs: {registered - set(_STUBS)}; "
        f"stubs with no service: {set(_STUBS) - registered}"
    )


# ── the BaseTaskService hook ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_triton_inference_short_circuits_in_stub_mode(stub_mode, nmt_stub_service):
    """The Triton HTTP call must not happen at all when stub mode is on."""
    result = await nmt_stub_service._call_triton_inference(
        triton_endpoint="http://triton.invalid:8000/v2/models/nmt/infer",
        triton_inputs=_text_inputs(10),
        triton_outputs=["OUTPUT_TEXT"],
    )

    assert result["outputs"][0]["name"] == "OUTPUT_TEXT"


@pytest.fixture
def nmt_stub_service():
    from services.nmt_service import NMTTaskService
    return NMTTaskService(service_info={
        "name": "nmt", "endpoint": "http://triton.invalid:8000",
        "api_key": None, "adapter_config": {},
    })
