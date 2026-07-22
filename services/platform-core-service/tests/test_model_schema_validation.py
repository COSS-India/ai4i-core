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
        languages=[{"sourceLanguage": "en"}],
        license="mit",
        domain=["general"],
        inferenceEndPoint={"callbackUrl": "http://localhost:8000/infer", "schema": {}},
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


# ── Partial PATCH of inferenceEndPoint doesn't need callbackUrl/schema ─────


def test_patch_inference_endpoint_adapter_config_only():
    payload = ModelUpdateRequest(
        modelId="abc123",
        version="1.0",
        inferenceEndPoint={"adapterConfig": {"version": "1"}},
    )
    assert payload.inferenceEndPoint.adapter_config == {"version": "1"}
    assert payload.inferenceEndPoint.callbackUrl is None


def test_patch_inference_endpoint_is_multilingual_enabled_only():
    payload = ModelUpdateRequest(
        modelId="abc123",
        version="1.0",
        inferenceEndPoint={"isMultilingualEnabled": True},
    )
    assert payload.inferenceEndPoint.isMultilingualEnabled is True
    assert payload.inferenceEndPoint.endpoint_schema is None
