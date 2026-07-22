"""Unit tests: InferenceAPIEndPoint accepts adapterConfig (camelCase alias) (AI4IDS-1767/2478).

adapter_config moved from the model-level InferenceEndPoint (retired — the
review for AI4IDS-2478 dropped inferenceEndPoint from Model entirely) onto
Service's ULCA-conformant inferenceEndPoint, as an AI4Bharat extension field.
"""

import pytest
from pydantic import ValidationError

from app.schemas.common import AudioFormats, InferenceAPIEndPoint, TextFormats

_SAMPLE_ADAPTER_CONFIG = {
    "version": "1",
    "inputs": [{"tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.image_content"}],
    "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "text"}],
}

_BASE = {"callbackUrl": "http://localhost:8080", "schema": []}


# ── camelCase alias ────────────────────────────────────────────────────────────

def test_camel_case_adapterConfig_populates_field():
    ep = InferenceAPIEndPoint.model_validate({**_BASE, "adapterConfig": _SAMPLE_ADAPTER_CONFIG})
    assert ep.adapter_config == _SAMPLE_ADAPTER_CONFIG


def test_snake_case_adapter_config_also_works():
    ep = InferenceAPIEndPoint.model_validate({**_BASE, "adapter_config": _SAMPLE_ADAPTER_CONFIG})
    assert ep.adapter_config == _SAMPLE_ADAPTER_CONFIG


# ── None by default ───────────────────────────────────────────────────────────

def test_missing_adapter_config_defaults_to_none():
    ep = InferenceAPIEndPoint.model_validate(_BASE)
    assert ep.adapter_config is None


# ── Serialization round-trip ──────────────────────────────────────────────────

def test_serializes_with_camel_case_key():
    ep = InferenceAPIEndPoint.model_validate({**_BASE, "adapterConfig": _SAMPLE_ADAPTER_CONFIG})
    dumped = ep.model_dump(by_alias=True)
    assert "adapterConfig" in dumped
    assert dumped["adapterConfig"] == _SAMPLE_ADAPTER_CONFIG


def test_serializes_with_snake_case_key_when_no_alias():
    ep = InferenceAPIEndPoint.model_validate({**_BASE, "adapterConfig": _SAMPLE_ADAPTER_CONFIG})
    dumped = ep.model_dump(by_alias=False)
    assert "adapter_config" in dumped
    assert dumped["adapter_config"] == _SAMPLE_ADAPTER_CONFIG


# ── schema is mandatory (ULCA InferenceAPIEndPoint.schema) ────────────────────

def test_missing_schema_key_rejected():
    with pytest.raises(ValidationError):
        InferenceAPIEndPoint.model_validate({"callbackUrl": "http://localhost:8080"})


# ── minLength/maxLength constraints (ULCA InferenceAPIEndPoint) ───────────────

@pytest.mark.parametrize("field", ["providerName", "serviceId", "infraDescription", "inferenceModelId"])
def test_short_optional_string_fields_rejected(field):
    with pytest.raises(ValidationError):
        InferenceAPIEndPoint.model_validate({**_BASE, field: "abc"})


@pytest.mark.parametrize("field", ["providerName", "serviceId", "infraDescription", "inferenceModelId"])
def test_valid_length_optional_string_fields_accepted(field):
    ep = InferenceAPIEndPoint.model_validate({**_BASE, field: "Dhruva"})
    assert getattr(ep, field) == "Dhruva"


# ── supportedInputFormats/supportedOutputFormats (ULCA AudioFormats|TextFormats) ──

def test_supported_input_formats_accepts_audio_shape():
    ep = InferenceAPIEndPoint.model_validate({**_BASE, "supportedInputFormats": {"audio": ["wav", "mp3"]}})
    assert isinstance(ep.supportedInputFormats, AudioFormats)
    assert ep.supportedInputFormats.audio == ["wav", "mp3"]


def test_supported_output_formats_accepts_text_shape():
    ep = InferenceAPIEndPoint.model_validate({**_BASE, "supportedOutputFormats": {"text": ["srt", "transcript"]}})
    assert isinstance(ep.supportedOutputFormats, TextFormats)
    assert ep.supportedOutputFormats.text == ["srt", "transcript"]


def test_supported_input_formats_rejects_invalid_audio_value():
    with pytest.raises(ValidationError):
        InferenceAPIEndPoint.model_validate({**_BASE, "supportedInputFormats": {"audio": ["not-a-format"]}})


def test_supported_formats_rejects_unrecognized_shape():
    with pytest.raises(ValidationError):
        InferenceAPIEndPoint.model_validate({**_BASE, "supportedInputFormats": {"video": ["mp4"]}})
