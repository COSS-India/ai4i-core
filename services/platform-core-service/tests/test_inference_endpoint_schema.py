"""Unit tests: InferenceEndPoint accepts adapterConfig (camelCase alias) (AI4IDS-1767)."""

import pytest
from app.schemas.common import InferenceEndPoint

_SAMPLE_ADAPTER_CONFIG = {
    "version": "1",
    "inputs": [{"tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.image_content"}],
    "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "text"}],
}


# ── camelCase alias ────────────────────────────────────────────────────────────

def test_camel_case_adapterConfig_populates_field():
    ep = InferenceEndPoint.model_validate({"adapterConfig": _SAMPLE_ADAPTER_CONFIG})
    assert ep.adapter_config == _SAMPLE_ADAPTER_CONFIG


def test_snake_case_adapter_config_also_works():
    ep = InferenceEndPoint.model_validate({"adapter_config": _SAMPLE_ADAPTER_CONFIG})
    assert ep.adapter_config == _SAMPLE_ADAPTER_CONFIG


# ── None by default ───────────────────────────────────────────────────────────

def test_missing_adapter_config_defaults_to_none():
    ep = InferenceEndPoint.model_validate({})
    assert ep.adapter_config is None


# ── Serialization round-trip ──────────────────────────────────────────────────

def test_serializes_with_camel_case_key():
    ep = InferenceEndPoint.model_validate({"adapterConfig": _SAMPLE_ADAPTER_CONFIG})
    dumped = ep.model_dump(by_alias=True)
    assert "adapterConfig" in dumped
    assert dumped["adapterConfig"] == _SAMPLE_ADAPTER_CONFIG


def test_serializes_with_snake_case_key_when_no_alias():
    ep = InferenceEndPoint.model_validate({"adapterConfig": _SAMPLE_ADAPTER_CONFIG})
    dumped = ep.model_dump(by_alias=False)
    assert "adapter_config" in dumped
    assert dumped["adapter_config"] == _SAMPLE_ADAPTER_CONFIG
