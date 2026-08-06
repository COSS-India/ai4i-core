"""Validation-boundary tests for the ULCA-conformant Model schema (AI4IDS-2478).

Covers the gaps flagged in review: the required trainingDataset on create,
license casing/rejection, LanguagePair enum rejection, licenseUrl length, and
that a partial PATCH of inferenceEndPoint no longer needs callbackUrl/schema.
"""

import pytest
from pydantic import ValidationError

from app.schemas.common import LanguagePair
from app.schemas.model_management.model import ModelCreateRequest, ModelUpdateRequest


def _base_payload(**overrides):
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


# ── trainingDataset is required on create ──────────────────────────────────


def test_training_dataset_required_on_create():
    payload = _base_payload()
    del payload["trainingDataset"]
    with pytest.raises(ValidationError, match="trainingDataset"):
        ModelCreateRequest(**payload)


def test_training_dataset_provided_succeeds():
    req = ModelCreateRequest(**_base_payload())
    assert req.trainingDataset.description == "test training dataset"


# ── license casing / rejection ─────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [("mit", "mit"), ("MIT", "mit"), ("Mit", "mit")])
def test_license_case_insensitive_normalizes(raw, expected):
    req = ModelCreateRequest(**_base_payload(license=raw))
    assert req.license == expected


def test_license_unknown_value_rejected():
    with pytest.raises(ValidationError, match="Invalid license"):
        ModelCreateRequest(**_base_payload(license="Apache-2.0"))


# ── LanguagePair enum rejection ────────────────────────────────────────────


def test_language_pair_valid_code_accepted():
    pair = LanguagePair(sourceLanguage="hi", targetLanguage="en")
    assert pair.sourceLanguage.value == "hi"
    assert pair.targetLanguage.value == "en"


def test_language_pair_invalid_code_rejected():
    with pytest.raises(ValidationError):
        LanguagePair(sourceLanguage="fr")


def test_create_request_rejects_unsupported_language_code():
    with pytest.raises(ValidationError):
        ModelCreateRequest(**_base_payload(languages=[{"sourceLanguage": "fr"}]))


# ── licenseUrl length matches the mm_models.license_url column (500) ──────


def test_license_url_within_max_length_accepted():
    req = ModelCreateRequest(**_base_payload(licenseUrl="http://example.com/license"))
    assert req.licenseUrl == "http://example.com/license"


def test_license_url_over_max_length_rejected():
    with pytest.raises(ValidationError, match="licenseUrl"):
        ModelCreateRequest(**_base_payload(licenseUrl="http://example.com/" + "x" * 500))


# ── inferenceEndPoint rejected with a clear error ─────────────────────────────


def test_create_with_inference_end_point_rejected():
    with pytest.raises(ValidationError, match="inferenceEndPoint.*removed"):
        ModelCreateRequest(**_base_payload(inferenceEndPoint={"callbackUrl": "http://x", "schema": {}}))


def test_patch_with_inference_end_point_rejected():
    with pytest.raises(ValidationError, match="inferenceEndPoint.*removed"):
        ModelUpdateRequest(modelId="abc123", version="1.0", inferenceEndPoint={"callbackUrl": "http://x"})


# ── schema requires model_name ─────────────────────────────────────────────────


def test_create_schema_without_model_name_rejected():
    with pytest.raises(ValidationError, match="model_name"):
        ModelCreateRequest(**_base_payload(**{"schema": {"taskType": "translation"}}))


def test_create_schema_with_model_name_accepted():
    req = ModelCreateRequest(**_base_payload(**{"schema": {"model_name": "my-model"}}))
    assert req.endpoint_schema == {"model_name": "my-model"}


def test_patch_schema_without_model_name_rejected():
    with pytest.raises(ValidationError, match="model_name"):
        ModelUpdateRequest(modelId="abc123", version="1.0", **{"schema": {"taskType": "translation"}})


# ── adapterConfig requires inputs and outputs ──────────────────────────────────


def test_create_adapter_config_without_inputs_rejected():
    with pytest.raises(ValidationError, match="inputs"):
        ModelCreateRequest(**_base_payload(adapterConfig={"outputs": [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "text"}]}))


def test_create_adapter_config_without_outputs_rejected():
    with pytest.raises(ValidationError, match="outputs"):
        ModelCreateRequest(**_base_payload(adapterConfig={"inputs": [{"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}]}))


def test_create_adapter_config_with_inputs_and_outputs_accepted():
    adapter = {
        "inputs": [{"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "text"}],
    }
    req = ModelCreateRequest(**_base_payload(adapterConfig=adapter))
    assert req.adapterConfig == adapter


# ── Partial PATCH — adapterConfig and schema are now top-level fields ─────────


def test_patch_adapter_config_only():
    payload = ModelUpdateRequest(
        modelId="abc123",
        version="1.0",
        adapterConfig={"version": "1"},
    )
    assert payload.adapterConfig == {"version": "1"}
    assert payload.endpoint_schema is None


def test_patch_is_multilingual_only():
    payload = ModelUpdateRequest(
        modelId="abc123",
        version="1.0",
        isMultilingual=True,
    )
    assert payload.isMultilingual is True
    assert payload.adapterConfig is None
