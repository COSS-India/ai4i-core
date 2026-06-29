"""Unit tests for the Triton input/output mappers (AI4IDS-1981).

Proves a single output_transform reproduces the task-type output for a trivial
case (NMT, input pairing) and the hardest case (Speaker Diarization, JSON-blob
parse + sort + distinct + count + arithmetic), byte-for-byte, and that the input
mapper renders typed tensors / enforces required inputs.
"""

import sys

import pytest

sys.path.insert(0, ".")

from services.base.task_service import AdapterMappingConfig
from services.base.triton_input_mapper import TritonInputMapper
from services.base.triton_output_mapper import OutputTensorDeclaration, TritonOutputMapper


def _build_mappers(adapter_config: dict):
    """Build the input + output mappers from a raw adapter_config dict, the same
    way BaseTaskService does at request time."""
    cfg = AdapterMappingConfig.model_validate(adapter_config)
    return TritonInputMapper(cfg.inputs), TritonOutputMapper(cfg.outputs, cfg.output_transform)


# ── NMT: input pairing, no JSON parse ──────────────────────────────────────────

_NMT_TRANSFORM = """(
  $inp := inputs;
  { "output": [ $map(tensors.OUTPUT_TEXT, function($t, $i) { {"source": $inp[$i].source, "target": $t} }) ] }
)"""


def test_nmt_output_transform():
    mapper = TritonOutputMapper([OutputTensorDeclaration(tensor="OUTPUT_TEXT")], _NMT_TRANSFORM)
    triton_output = {"outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES",
                                  "shape": [2, 1], "data": ["नमस्ते", "अलविदा"]}]}
    decoded = mapper.decode([triton_output])
    result = mapper.transform(
        decoded,
        inputs=[{"source": "Hello"}, {"source": "Goodbye"}],
        request_config={"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    )
    assert result == {
        "output": [
            {"source": "Hello", "target": "नमस्ते"},
            {"source": "Goodbye", "target": "अलविदा"},
        ]
    }


# ── Speaker Diarization: JSON parse + aggregation ──────────────────────────────

_SD_TRANSFORM = """(
  $dr := tensors.DIARIZATION_RESULT[0];
  $sorted := $sort($dr.segments, function($a, $b) { $a.start_time > $b.start_time });
  $segs := $sorted.{
    "start": start_time, "end": end_time,
    "duration": $exists(duration) ? duration : end_time - start_time,
    "speaker": speaker
  };
  {
    "taskType": "speaker-diarization",
    "output": [{
      "total_segments": $count($segs),
      "num_speakers": $count($distinct($segs.speaker)),
      "speakers": $sort($distinct($segs.speaker)),
      "segments": $segs
    }],
    "config": {
      "serviceId": request.config.serviceId,
      "language": $exists(request.config.language) ? request.config.language : null
    }
  }
)"""


def test_speaker_diarization_output_transform():
    mapper = TritonOutputMapper(
        [OutputTensorDeclaration(tensor="DIARIZATION_RESULT", is_json=True)], _SD_TRANSFORM
    )
    diarization_json = (
        '{"segments": ['
        '{"start_time": 1.5, "end_time": 3.0, "speaker": "spk_1"},'
        '{"start_time": 0.0, "end_time": 1.5, "speaker": "spk_0", "duration": 1.5}'
        ']}'
    )
    triton_output = {"outputs": [{"name": "DIARIZATION_RESULT", "datatype": "BYTES",
                                  "shape": [1, 1], "data": [diarization_json]}]}
    decoded = mapper.decode([triton_output])
    result = mapper.transform(
        decoded, inputs=[], request_config={"serviceId": "sd-1"}
    )
    assert result == {
        "taskType": "speaker-diarization",
        "output": [{
            "total_segments": 2,
            "num_speakers": 2,
            "speakers": ["spk_0", "spk_1"],
            "segments": [
                {"start": 0.0, "end": 1.5, "duration": 1.5, "speaker": "spk_0"},
                {"start": 1.5, "end": 3.0, "duration": 1.5, "speaker": "spk_1"},
            ],
        }],
        "config": {"serviceId": "sd-1", "language": None},
    }


# ── Config-load validation ─────────────────────────────────────────────────────

def test_invalid_expression_raises_at_construction():
    with pytest.raises(RuntimeError, match="Invalid output_transform"):
        TritonOutputMapper([OutputTensorDeclaration(tensor="OUTPUT_TEXT")],
                           "{ this is not valid jsonata (((")


def test_v2_schema_parses():
    cfg = AdapterMappingConfig.model_validate({
        "schema_version": "2.0",
        "inputs": [{"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1],
                    "value_path": "input.source"}],
        "outputs": [{"tensor": "OUTPUT_TEXT"}, {"tensor": "DIARIZATION_RESULT", "is_json": True}],
        "output_transform": _NMT_TRANSFORM,
    })
    assert cfg.schema_version == "2.0"
    assert [o.tensor for o in cfg.outputs] == ["OUTPUT_TEXT", "DIARIZATION_RESULT"]
    assert cfg.outputs[1].is_json is True


# ── Input + output mappers together (built as BaseTaskService does) ─────────────

def test_mapper_input_render_and_output_transform():
    input_mapper, output_mapper = _build_mappers({
        "schema_version": "2.0",
        "inputs": [
            {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
            {"tensor": "SRC", "dtype": "BYTES", "shape": [-1, 1],
             "value_path": "request.config.language.sourceLanguage"},
        ],
        "outputs": [{"tensor": "OUTPUT_TEXT"}],
        "output_transform": _NMT_TRANSFORM,
    })

    inputs_list = input_mapper.compose_triton_kserve_v2_payload(
        [{"source": "Hello"}], {"language": {"sourceLanguage": "en"}}
    )
    assert output_mapper.output_names == ["OUTPUT_TEXT"]
    assert {i["name"] for i in inputs_list} == {"INPUT_TEXT", "SRC"}

    raw = {"outputs": [{"name": "OUTPUT_TEXT", "data": ["नमस्ते"]}]}
    out = output_mapper.transform(
        output_mapper.decode([raw]), inputs=[{"source": "Hello"}], request_config={}
    )
    assert out == {"output": [{"source": "Hello", "target": "नमस्ते"}]}


# ── Required-input enforcement (replaces per-service validate_request) ──────────

def test_missing_required_input_raises_value_error():
    """A value_path with no `value` default that the request omits is a client
    error (ValueError -> 400), not a server fault."""
    input_mapper, _ = _build_mappers({
        "schema_version": "2.0",
        "inputs": [
            {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
            {"tensor": "LANG", "dtype": "BYTES", "shape": [-1, 1],
             "value_path": "request.config.language.sourceLanguage"},
        ],
        "outputs": [{"tensor": "OUTPUT_TEXT"}],
        "output_transform": _NMT_TRANSFORM,
    })
    with pytest.raises(ValueError, match="sourceLanguage"):
        input_mapper.compose_triton_kserve_v2_payload([{"source": "Hi"}], {"language": {}})


def test_optional_input_uses_value_default():
    """A declaration carrying both value_path and `value` falls back to the
    default when the request omits the key (e.g. numSpeakers)."""
    input_mapper, _ = _build_mappers({
        "schema_version": "2.0",
        "inputs": [
            {"tensor": "AUDIO", "dtype": "BYTES", "shape": [1, 1], "value_path": "input.audioContent"},
            {"tensor": "NUM_SPEAKERS", "dtype": "BYTES", "shape": [1, 1],
             "value_path": "request.config.numSpeakers", "value": ""},
        ],
        "outputs": [{"tensor": "OUT"}],
    })
    inputs_list = input_mapper.compose_triton_kserve_v2_payload([{"audioContent": "b64"}], {})
    num_speakers = next(i for i in inputs_list if i["name"] == "NUM_SPEAKERS")
    assert num_speakers["data"] == [""]
