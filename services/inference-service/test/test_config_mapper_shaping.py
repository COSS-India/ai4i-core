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


# ── transform: json_parse ─────────────────────────────────────────────────────

def test_transform_json_parse_returns_full_dict():
    """Diarization/ALD envelopes: the whole parsed object is the response."""
    mapper = _mapper([
        {"tensor": "DIARIZATION_RESULT", "dtype": "BYTES", "maps_to": "diarization",
         "transform": "json_parse"},
    ])
    payload = '{"segments": [{"start": 0.0, "end": 1.5, "speaker": "spk0"}]}'
    mapped = mapper.map_outputs(_triton_response("DIARIZATION_RESULT", [payload], [1, 1]))
    assert mapped["diarization"] == [{"segments": [{"start": 0.0, "end": 1.5, "speaker": "spk0"}]}]


def test_transform_json_parse_non_json_passes_through():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "text", "transform": "json_parse"},
    ])
    mapped = mapper.map_outputs(_triton_response("OUT", ["plain text"], [1, 1]))
    assert mapped["text"] == ["plain text"]


# ── transform: base64_encode ──────────────────────────────────────────────────

def test_transform_base64_encode():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "content", "transform": "base64_encode"},
    ])
    mapped = mapper.map_outputs(_triton_response("OUT", ["hello"], [1, 1]))
    assert mapped["content"] == [base64.b64encode(b"hello").decode()]


# ── transform: unwrap_scalar ──────────────────────────────────────────────────

def test_transform_unwrap_scalar():
    mapper = _mapper([
        {"tensor": "OUT", "dtype": "BYTES", "maps_to": "text", "transform": "unwrap_scalar"},
    ])
    mapped = mapper.map_outputs(_triton_response("OUT", ["only"], [1, 1]))
    assert mapped["text"] == "only"


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
    mapped = mapper.map_outputs(_triton_response("OUT", [payload], [1, 1]))
    assert mapped["inner"] == [{"a": 1}]


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
