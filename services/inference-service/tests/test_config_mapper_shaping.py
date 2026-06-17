"""Unit tests: config-driven output transforms and response shaping.

Covers the adapter_config output fields beyond maps_to/json_field:
  transform        — json_parse | base64_encode | unwrap_scalar
  response_key     — 'output[].<key>' rename in the shaped response
  pair_with_input  — index-for-index input field pairing
"""

import base64
import sys

import pytest

sys.path.insert(0, ".")

from services.base.config_mapper import GenericTritonMapper


def _mapper(outputs, call_mode="batch"):
    return GenericTritonMapper({
        "version": "1.0",
        "call_mode": call_mode,
        "inputs": [
            {"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
        ],
        "outputs": outputs,
    })


def _triton_response(name, data, shape):
    return {"outputs": [{"name": name, "datatype": "BYTES", "shape": shape, "data": data}]}


def _items(mapper, response):
    """Transforms apply per output item (to_output_items), after map_outputs."""
    return mapper.to_output_items(mapper.map_outputs(response))


# ── transform: json_parse ─────────────────────────────────────────────────────

def test_transform_json_parse_returns_full_dict():
    """Diarization/ALD envelopes: the whole parsed object is the response."""
    mapper = _mapper([
        {"tensor": "DIARIZATION_RESULT", "dtype": "BYTES", "maps_to": "diarization",
         "transform": "json_parse"},
    ])
    payload = '{"segments": [{"start": 0.0, "end": 1.5, "speaker": "spk0"}]}'
    items = _items(mapper, _triton_response("DIARIZATION_RESULT", [payload], [1, 1]))
    assert items[0]["diarization"] == {"segments": [{"start": 0.0, "end": 1.5, "speaker": "spk0"}]}


def test_transform_json_parse_non_json_passes_through():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "text", "transform": "json_parse"},
    ])
    items = _items(mapper, _triton_response("OUT", ["plain text"], [1, 1]))
    assert items[0]["text"] == "plain text"


# ── transform: base64_encode ──────────────────────────────────────────────────

def test_transform_base64_encode():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "content", "transform": "base64_encode"},
    ])
    items = _items(mapper, _triton_response("OUT", ["hello"], [1, 1]))
    assert items[0]["content"] == base64.b64encode(b"hello").decode()


# ── transform: unwrap_scalar ──────────────────────────────────────────────────

def test_transform_unwrap_scalar():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "text", "transform": "unwrap_scalar"},
    ])
    items = _items(mapper, _triton_response("OUT", ["only"], [1, 1]))
    assert items[0]["text"] == "only"


# ── transform: validation ─────────────────────────────────────────────────────

def test_unknown_transform_rejected_at_config_load():
    with pytest.raises(RuntimeError, match="unsupported transform"):
        _mapper([
            {"tensor": "OUT", "dtype": "BYTES", "maps_to": "x", "transform": "rot13"},
        ])


def test_transform_composes_with_json_field():
    """json_field extracts a field; transform then applies to the extracted value."""
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "inner",
         "json_field": "nested", "transform": "json_parse"},
    ])
    payload = '{"nested": "{\\"a\\": 1}"}'
    items = _items(mapper, _triton_response("OUT", [payload], [1, 1]))
    assert items[0]["inner"] == {"a": 1}


# ── response_key ──────────────────────────────────────────────────────────────

def test_response_key_renames_maps_to_per_item():
    """ASR example from the spec: transcript -> output[].source."""
    mapper = _mapper([
        {"tensor": "TRANSCRIBED_TEXT", "dtype": "BYTES", "maps_to": "transcript",
         "response_key": "output[].source"},
    ])
    shaped = mapper.shape_output_items([{"transcript": "hello world"}], [{}])
    assert shaped == [{"source": "hello world"}]


def test_invalid_response_key_rejected_at_config_load():
    with pytest.raises(RuntimeError, match="response_key must be"):
        _mapper([
            {"tensor": "OUT", "dtype": "BYTES", "maps_to": "x",
             "response_key": "result.text"},
        ])


# ── pair_with_input ───────────────────────────────────────────────────────────

def test_pair_with_input_pairs_by_index():
    """Text pairing: input.source paired into each output item."""
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "target",
         "pair_with_input": "input.source"},
    ])
    shaped = mapper.shape_output_items(
        [{"target": "नमस्ते"}, {"target": "धन्यवाद"}],
        [{"source": "hello"}, {"source": "thanks"}],
    )
    assert shaped == [
        {"target": "नमस्ते", "source": "hello"},
        {"target": "धन्यवाद", "source": "thanks"},
    ]


def test_pair_with_input_resolves_camel_case():
    """audio.audio_uri must find audioUri on the input item."""
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "diarization",
         "pair_with_input": "audio.audio_uri"},
    ])
    shaped = mapper.shape_output_items(
        [{"diarization": {"segments": []}}],
        [{"audioUri": "https://example.com/a.wav"}],
    )
    assert shaped[0]["audio_uri"] == "https://example.com/a.wav"


def test_pair_with_input_missing_input_defaults_empty():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "target",
         "pair_with_input": "input.source"},
    ])
    shaped = mapper.shape_output_items([{"target": "x"}], [])
    assert shaped == [{"target": "x", "source": ""}]


# ── has_response_shaping ──────────────────────────────────────────────────────

def test_has_response_shaping_detection():
    plain = _mapper([{"tensor": "O", "dtype": "BYTES", "maps_to": "target"}])
    shaped = _mapper([{"tensor": "O", "dtype": "BYTES", "maps_to": "t",
                       "response_key": "output[].target"}])
    assert not plain.has_response_shaping()
    assert shaped.has_response_shaping()


# ── transform: wrap_list + chains ─────────────────────────────────────────────

def test_transform_chain_json_parse_wrap_list():
    """LANG_DET contract: parsed prediction object always arrives as a list."""
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "langPrediction",
         "transform": ["json_parse", "wrap_list"]},
    ])
    payload = '{"langCode": "hin_Deva", "confidence": 0.69}'
    items = _items(mapper, _triton_response("OUT", [payload], [1, 1]))
    assert items[0]["langPrediction"] == [{"langCode": "hin_Deva", "confidence": 0.69}]


def test_wrap_list_empty_value_yields_empty_list():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "x", "transform": "wrap_list"},
    ])
    items = _items(mapper, _triton_response("OUT", [""], [1, 1]))
    assert items[0]["x"] == []


# ── response_key splat: 'output[]' ────────────────────────────────────────────

def test_splat_parsed_dict_becomes_the_item():
    """Diarization: the parsed envelope IS the output item."""
    mapper = _mapper([
        {"tensor": "DIARIZATION_RESULT", "dtype": "BYTES", "maps_to": "diarization_json",
         "transform": "json_parse", "response_key": "output[]"},
    ])
    payload = '{"total_segments": 1, "segments": [{"start_time": 0.0}], "target_language": "all"}'
    items = _items(mapper, _triton_response("DIARIZATION_RESULT", [payload], [1, 1]))
    shaped = mapper.shape_output_items(items, [{}])
    assert shaped == [{"total_segments": 1, "segments": [{"start_time": 0.0}], "target_language": "all"}]


def test_splat_non_dict_stays_under_maps_to():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "diarization_json",
         "transform": "json_parse", "response_key": "output[]"},
    ])
    items = _items(mapper, _triton_response("OUT", ["not json"], [1, 1]))
    shaped = mapper.shape_output_items(items, [{}])
    assert shaped == [{"diarization_json": "not json"}]


# ── static_item_fields + envelope ─────────────────────────────────────────────

def _mapper_with_response(outputs, response):
    return GenericTritonMapper({
        "version": "1.0",
        "inputs": [{"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": outputs,
        "response": response,
    })


def test_static_item_fields_added_when_absent():
    """OCR contract: rename text->source, constant empty target."""
    mapper = _mapper_with_response(
        [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "text", "response_key": "output[].source"}],
        {"static_item_fields": {"target": ""}},
    )
    shaped = mapper.shape_output_items([{"text": "hello"}], [{}])
    assert shaped == [{"source": "hello", "target": ""}]
    assert list(shaped[0]) == ["source", "target"]


def test_envelope_task_type_and_config_keys():
    mapper = _mapper_with_response(
        [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "language_code"}],
        {"task_type": "audio-lang-detection", "config_keys": ["serviceId"]},
    )
    out = mapper.build_response_envelope([{"language_code": "hi"}], {"serviceId": "abc", "other": 1})
    assert out == {"taskType": "audio-lang-detection",
                   "output": [{"language_code": "hi"}],
                   "config": {"serviceId": "abc"}}
    assert list(out) == ["taskType", "output", "config"]


def test_envelope_include_config_false_omits_key():
    mapper = _mapper_with_response(
        [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "transcript", "response_key": "output[].source"}],
        {"include_config": False, "static_item_fields": {"nBestTokens": None}},
    )
    shaped = mapper.shape_output_items([{"transcript": ""}], [{}])
    out = mapper.build_response_envelope(shaped, {"serviceId": "x"})
    assert out == {"output": [{"source": "", "nBestTokens": None}]}


def test_pair_fields_lead_the_item():
    """Pairing puts the input field first (XLIT/LANG_DET ordering)."""
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "target", "pair_with_input": "input.source"},
    ])
    shaped = mapper.shape_output_items([{"target": "नमस्ते"}], [{"source": "namaste"}])
    assert list(shaped[0]) == ["source", "target"]


def test_pair_out_of_range_input_defaults_empty():
    """XLIT top-k: extra batch items pair with '' when inputs run out."""
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "target", "pair_with_input": "input.source"},
    ])
    shaped = mapper.shape_output_items(
        [{"target": "a"}, {"target": "b"}], [{"source": "x"}])
    assert shaped == [{"source": "x", "target": "a"}, {"source": "", "target": "b"}]
