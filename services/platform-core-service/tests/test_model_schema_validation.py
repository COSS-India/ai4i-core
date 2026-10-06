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
        # Required for every task type except llm/pipeline — see
        # _validate_class_instance_required. Default task above is "nmt".
        classInstance="NMTTaskService",
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
        "version": "1.0",
        "inputs": [{"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "text"}],
    }
    req = ModelCreateRequest(**_base_payload(adapterConfig=adapter))
    assert req.adapterConfig == adapter


def test_create_adapter_config_without_version_rejected():
    adapter = {
        "inputs": [{"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "text"}],
    }
    with pytest.raises(ValidationError, match="version"):
        ModelCreateRequest(**_base_payload(adapterConfig=adapter))


def test_create_adapter_config_input_without_value_path_or_value_rejected():
    adapter = {
        "version": "1.0",
        "inputs": [{"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1]}],
        "outputs": [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "text"}],
    }
    with pytest.raises(ValidationError, match="value_path"):
        ModelCreateRequest(**_base_payload(adapterConfig=adapter))


def test_create_adapter_config_unsupported_dtype_rejected():
    adapter = {
        "version": "1.0",
        "inputs": [{"tensor": "IN", "dtype": "NOT_A_DTYPE", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "text"}],
    }
    with pytest.raises(ValidationError, match="dtype"):
        ModelCreateRequest(**_base_payload(adapterConfig=adapter))


def test_create_tts_adapter_config_requires_output_generated_audio_tensor():
    adapter = {
        "version": "1.0",
        "inputs": [{"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [1], "value_path": "input.source"}],
        "outputs": [{"tensor": "SOME_OTHER_NAME", "dtype": "FP32", "maps_to": "audio_data"}],
    }
    with pytest.raises(ValidationError, match="OUTPUT_GENERATED_AUDIO"):
        ModelCreateRequest(**_base_payload(task={"type": "tts"}, adapterConfig=adapter))


def test_create_ner_adapter_config_requires_json_parse_transform():
    adapter = {
        "version": "1.0",
        "inputs": [{"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target"}],
    }
    with pytest.raises(ValidationError, match="json_parse"):
        ModelCreateRequest(**_base_payload(task={"type": "ner"}, adapterConfig=adapter))


def test_create_llm_adapter_config_requires_model_name():
    adapter = {
        "version": "1.0",
        "inputs": [{"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": [{"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target"}],
    }
    with pytest.raises(ValidationError, match="model_name"):
        ModelCreateRequest(**_base_payload(task={"type": "llm"}, adapterConfig=adapter))


def test_create_llm_adapter_config_skips_triton_tensor_checks():
    """llm never reaches GenericTritonMapper — the proxy reads only
    adapter_config.model_name — so empty inputs/outputs and no version must
    still be accepted, as they were before these checks existed."""
    adapter = {"model_name": "meta-llama/Llama-3-8B", "inputs": [], "outputs": []}
    req = ModelCreateRequest(**_base_payload(task={"type": "llm"}, adapterConfig=adapter))
    assert req.adapterConfig == adapter


def _adapter_with_output(**output_fields):
    return {
        "version": "1.0",
        "inputs": [{"tensor": "IN", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}],
        "outputs": [{"tensor": "OUT", "dtype": "BYTES", "maps_to": "text", **output_fields}],
    }


@pytest.mark.parametrize("transform", ["json_pars", ["json_parse", "not_a_transform"]])
def test_create_adapter_config_unsupported_output_transform_rejected(transform):
    with pytest.raises(ValidationError, match="transform"):
        ModelCreateRequest(**_base_payload(adapterConfig=_adapter_with_output(transform=transform)))


@pytest.mark.parametrize("transform", ["json_parse", ["json_parse", "wrap_list"]])
def test_create_adapter_config_supported_output_transform_accepted(transform):
    ModelCreateRequest(**_base_payload(adapterConfig=_adapter_with_output(transform=transform)))


@pytest.mark.parametrize("response_key", ["output", "output[].", "result[].text", "output[].a.b"])
def test_create_adapter_config_invalid_response_key_rejected(response_key):
    with pytest.raises(ValidationError, match="response_key"):
        ModelCreateRequest(**_base_payload(adapterConfig=_adapter_with_output(response_key=response_key)))


@pytest.mark.parametrize("response_key", ["output[]", "output[].source"])
def test_create_adapter_config_valid_response_key_accepted(response_key):
    ModelCreateRequest(**_base_payload(adapterConfig=_adapter_with_output(response_key=response_key)))


def test_create_schema_task_type_mismatch_rejected():
    schema = {
        "taskType": "nmt",
        "model_name": "x",
        "request": {},
        "response": {},
    }
    with pytest.raises(ValidationError, match="does not match"):
        ModelCreateRequest(**_base_payload(
            task={"type": "asr"},
            classInstance="ASRTaskService",
            **{"schema": schema},
        ))


def test_create_schema_task_type_match_accepted():
    schema = {
        "taskType": "asr",
        "model_name": "x",
        "request": {},
        "response": {},
    }
    req = ModelCreateRequest(**_base_payload(
        task={"type": "asr"},
        classInstance="ASRTaskService",
        **{"schema": schema},
    ))
    assert req.endpoint_schema == schema


def test_create_schema_task_type_nmt_translation_equivalence_accepted():
    # nmt <-> translation are treated as equivalent, not an exact-match mismatch.
    schema = {
        "taskType": "translation",
        "model_name": "x",
        "request": {},
        "response": {},
    }
    req = ModelCreateRequest(**_base_payload(**{"schema": schema}))
    assert req.endpoint_schema == schema


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
])
def test_create_boolean_field_accepts_bool(field, value):
    req = ModelCreateRequest(**_base_payload(**{field: value}))
    assert getattr(req, field) is value


def test_create_is_sync_api_false_accepts_bool_with_async_details():
    # isSyncApi=False requires asyncApiDetails (see
    # ModelCreateRequest._validate_async_details_required_when_async) —
    # unlike the other boolean fields, it can't be tested standalone.
    req = ModelCreateRequest(**_base_payload(
        isSyncApi=False,
        asyncApiDetails={"pollingUrl": "https://example.com/poll", "pollInterval": 1000},
    ))
    assert req.isSyncApi is False


def test_create_is_sync_api_false_without_async_details_rejected():
    with pytest.raises(ValidationError, match="asyncApiDetails"):
        ModelCreateRequest(**_base_payload(isSyncApi=False))


@pytest.mark.parametrize("field", ["isLangDetectionEnabled", "isMultilingual", "isSyncApi"])
def test_patch_boolean_field_rejects_string(field):
    with pytest.raises(ValidationError, match=field):
        ModelUpdateRequest(modelId="abc123", version="1.0", **{field: "false"})


# ── classInstance required for every task type except llm/pipeline ────────────


def test_create_missing_class_instance_rejected_for_non_llm_task():
    payload = _base_payload()
    del payload["classInstance"]
    with pytest.raises(ValidationError, match="classInstance"):
        ModelCreateRequest(**payload)


def test_create_class_instance_not_required_for_llm():
    payload = _base_payload(task={"type": "llm"})
    del payload["classInstance"]
    req = ModelCreateRequest(**payload)
    assert req.classInstance is None


def test_create_class_instance_not_required_for_pipeline():
    payload = _base_payload(task={"type": "pipeline"})
    del payload["classInstance"]
    req = ModelCreateRequest(**payload)
    assert req.classInstance is None


def test_create_class_instance_provided_for_non_llm_task_accepted():
    req = ModelCreateRequest(**_base_payload(task={"type": "asr"}, classInstance="ASRTaskService"))
    assert req.classInstance == "ASRTaskService"
