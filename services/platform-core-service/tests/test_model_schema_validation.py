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


# ── schema requires model_name/taskType/request/response together (create only) ─
# A Service created against this model later derives its own
# inferenceEndPoint.schema from these same four keys, and can't be given one
# manually — so an incomplete schema on CREATE can never be filled in
# downstream. PATCH deliberately stays at model_name-only (see
# ModelUpdateRequest._require_model_name_in_schema) — it replaces the stored
# schema outright, so re-enforcing completeness there would 422 a plain edit
# of a model whose stored schema predates this rule.

_COMPLETE_SCHEMA = {
    "model_name": "my-model",
    "taskType": "translation",
    "request": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    "response": {"output": [{"target": "string"}]},
}


def test_create_schema_without_model_name_rejected():
    with pytest.raises(ValidationError, match="model_name"):
        ModelCreateRequest(**_base_payload(**{"schema": {"taskType": "translation"}}))


def test_create_schema_with_only_model_name_rejected():
    with pytest.raises(ValidationError, match="taskType"):
        ModelCreateRequest(**_base_payload(**{"schema": {"model_name": "my-model"}}))


def test_create_schema_missing_request_and_response_rejected():
    """model_name and taskType alone aren't enough either — request/response
    are checked independently, not just implied by the other two being
    present."""
    with pytest.raises(ValidationError, match=r"request.*response|response.*request"):
        ModelCreateRequest(
            **_base_payload(**{"schema": {"model_name": "my-model", "taskType": "translation"}})
        )


def test_create_schema_with_unrecognized_task_type_rejected():
    """A taskType outside the recognized set (e.g. a value that isn't one of
    our TaskTypeEnum values or ULCA's own discriminator spellings) must be
    caught here — Service creation rejects it anyway, so this is strictly
    earlier, not different."""
    with pytest.raises(ValidationError, match="not a recognized task type"):
        ModelCreateRequest(
            **_base_payload(**{"schema": {**_COMPLETE_SCHEMA, "taskType": "text-generation"}})
        )


def test_create_complete_schema_accepted():
    req = ModelCreateRequest(**_base_payload(**{"schema": _COMPLETE_SCHEMA}))
    assert req.endpoint_schema == _COMPLETE_SCHEMA


def test_patch_schema_without_model_name_rejected():
    with pytest.raises(ValidationError, match="model_name"):
        ModelUpdateRequest(modelId="abc123", version="1.0", **{"schema": {"taskType": "translation"}})


def test_patch_incomplete_schema_accepted():
    """PATCH deliberately does NOT re-enforce taskType/request/response —
    only model_name — so a model whose stored schema predates the stricter
    create-time rule can still be edited without also having to backfill
    those three fields in the same request."""
    req = ModelUpdateRequest(modelId="abc123", version="1.0", **{"schema": {"model_name": "my-model"}})
    assert req.endpoint_schema == {"model_name": "my-model"}


def test_patch_complete_schema_accepted():
    req = ModelUpdateRequest(modelId="abc123", version="1.0", **{"schema": _COMPLETE_SCHEMA})
    assert req.endpoint_schema == _COMPLETE_SCHEMA


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


# ── StrictBool rejects strings for boolean fields ─────────────────────────────


@pytest.mark.parametrize("field", ["isLangDetectionEnabled", "isMultilingual", "isSyncApi"])
def test_create_boolean_field_rejects_string(field):
    with pytest.raises(ValidationError, match=field):
        ModelCreateRequest(**_base_payload(**{field: "true"}))


@pytest.mark.parametrize("field,value", [
    ("isLangDetectionEnabled", True),
    ("isLangDetectionEnabled", False),
    ("isMultilingual", True),
    ("isMultilingual", False),
    ("isSyncApi", True),
    ("isSyncApi", False),
])
def test_create_boolean_field_accepts_bool(field, value):
    req = ModelCreateRequest(**_base_payload(**{field: value}))
    assert getattr(req, field) is value


@pytest.mark.parametrize("field", ["isLangDetectionEnabled", "isMultilingual", "isSyncApi"])
def test_patch_boolean_field_rejects_string(field):
    with pytest.raises(ValidationError, match=field):
        ModelUpdateRequest(modelId="abc123", version="1.0", **{field: "false"})
