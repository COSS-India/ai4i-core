"""Unit tests: adapterConfig and schema are top-level fields on
ModelCreateRequest/ModelUpdateRequest after the inferenceEndPoint wrapper
was removed (AI4IDS-2697)."""

import pytest

from app.schemas.model_management.model import ModelCreateRequest, ModelUpdateRequest


def _base_create(**overrides):
    defaults = dict(
        name="test-model",
        version="1.0",
        description="A test model used for automated unit testing.",
        refUrl="http://example.com/model",
        task={"type": "nmt"},
        license="mit",
        domain=["general"],
        submitter={"name": "Test User"},
        trainingDataset={"description": "test training dataset"},
    )
    defaults.update(overrides)
    return defaults


_SAMPLE_ADAPTER_CONFIG = {
    "version": "1",
    "inputs": [{"tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.image_content"}],
    "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "text"}],
}


# ── adapterConfig on create ────────────────────────────────────────────────────

def test_create_with_adapter_config_populates_field():
    req = ModelCreateRequest(**_base_create(adapterConfig=_SAMPLE_ADAPTER_CONFIG))
    assert req.adapterConfig == _SAMPLE_ADAPTER_CONFIG


def test_create_without_adapter_config_defaults_to_none():
    req = ModelCreateRequest(**_base_create())
    assert req.adapterConfig is None


# ── schema (endpoint_schema) on create ────────────────────────────────────────

def test_create_with_schema_populates_field():
    schema = {"model_name": "my-model", "taskType": "translation"}
    req = ModelCreateRequest(**_base_create(**{"schema": schema}))
    assert req.endpoint_schema == schema


def test_create_without_schema_defaults_to_none():
    req = ModelCreateRequest(**_base_create())
    assert req.endpoint_schema is None


# ── PATCH (ModelUpdateRequest) ─────────────────────────────────────────────────

def test_patch_adapter_config_only_is_valid():
    req = ModelUpdateRequest(modelId="abc123", version="1.0", adapterConfig={"version": "2"})
    assert req.adapterConfig == {"version": "2"}
    assert req.endpoint_schema is None


def test_patch_schema_only_is_valid():
    req = ModelUpdateRequest(modelId="abc123", version="1.0", **{"schema": {"model_name": "updated"}})
    assert req.endpoint_schema == {"model_name": "updated"}
    assert req.adapterConfig is None


def test_patch_both_adapter_config_and_schema():
    req = ModelUpdateRequest(
        modelId="abc123",
        version="1.0",
        adapterConfig=_SAMPLE_ADAPTER_CONFIG,
        **{"schema": {"model_name": "my-model"}},
    )
    assert req.adapterConfig == _SAMPLE_ADAPTER_CONFIG
    assert req.endpoint_schema == {"model_name": "my-model"}
