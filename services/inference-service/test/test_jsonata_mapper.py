"""Unit tests for the v2 JSONata output mapper (AI4IDS-1981, slice 1).

Proves a single output_transform reproduces the task-type output for a trivial
case (NMT, input pairing) and the hardest case (Speaker Diarization, JSON-blob
parse + sort + distinct + count + arithmetic), byte-for-byte. Isolated: does not
touch the v1 GenericTritonMapper path.
"""

import sys

import pytest

sys.path.insert(0, ".")

from services.base.jsonata_mapper import AdapterMappingConfigV2, JsonataOutputMapper


# ── NMT: input pairing, no JSON parse ──────────────────────────────────────────

_NMT_TRANSFORM = """(
  $inp := inputs;
  { "output": [ $map(tensors.OUTPUT_TEXT, function($t, $i) { {"source": $inp[$i].source, "target": $t} }) ] }
)"""


def test_nmt_output_transform():
    mapper = JsonataOutputMapper(_NMT_TRANSFORM)
    triton_output = {"outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES",
                                  "shape": [2, 1], "data": ["नमस्ते", "अलविदा"]}]}
    tensors = mapper.decode_triton_outputs(triton_output)
    result = mapper.transform_output(
        tensors,
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
    mapper = JsonataOutputMapper(_SD_TRANSFORM, json_tensors=["DIARIZATION_RESULT"])
    diarization_json = (
        '{"segments": ['
        '{"start_time": 1.5, "end_time": 3.0, "speaker": "spk_1"},'
        '{"start_time": 0.0, "end_time": 1.5, "speaker": "spk_0", "duration": 1.5}'
        ']}'
    )
    triton_output = {"outputs": [{"name": "DIARIZATION_RESULT", "datatype": "BYTES",
                                  "shape": [1, 1], "data": [diarization_json]}]}
    tensors = mapper.decode_triton_outputs(triton_output)
    result = mapper.transform_output(
        tensors, inputs=[], request_config={"serviceId": "sd-1"}
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
        JsonataOutputMapper("{ this is not valid jsonata (((")


def test_v2_schema_parses():
    cfg = AdapterMappingConfigV2.model_validate({
        "schema_version": "2.0",
        "inputs": [{"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1],
                    "value_path": "input.source"}],
        "outputs": [{"tensor": "OUTPUT_TEXT"}, {"tensor": "DIARIZATION_RESULT", "is_json": True}],
        "output_transform": _NMT_TRANSFORM,
    })
    assert cfg.schema_version == "2.0"
    assert [o.tensor for o in cfg.outputs] == ["OUTPUT_TEXT", "DIARIZATION_RESULT"]
    assert cfg.outputs[1].is_json is True


# ── V2Mapper: v1 input render + JSONata output, one object ─────────────────────

def test_v2mapper_input_render_and_output_transform():
    from services.base.jsonata_mapper import V2Mapper

    mapper = V2Mapper({
        "schema_version": "2.0",
        "inputs": [
            {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
            {"tensor": "SRC", "dtype": "BYTES", "shape": [-1, 1],
             "value_path": "request.config.language.source_language"},
        ],
        "outputs": [{"tensor": "OUTPUT_TEXT"}],
        "output_transform": _NMT_TRANSFORM,
    })

    inputs_list, output_names = mapper.compose_triton_kserve_v2_payload(
        [{"source": "Hello"}], {"language": {"sourceLanguage": "en"}}
    )
    assert output_names == ["OUTPUT_TEXT"]
    assert {i["name"] for i in inputs_list} == {"INPUT_TEXT", "SRC"}

    raw = {"outputs": [{"name": "OUTPUT_TEXT", "data": ["नमस्ते"]}]}
    out = mapper.transform([raw], inputs=[{"source": "Hello"}], request_config={})
    assert out == {"output": [{"source": "Hello", "target": "नमस्ते"}]}
