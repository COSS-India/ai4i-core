"""Unit tests for app.services.model-management.serializers (AI4IDS-2478).

Covers _redact_inference_endpoint in isolation — the read-path half of the
inferenceApiKey.value secret handling (the write-path guard against the
sentinel round-tripping back into storage is covered separately in
test_model_management.py::TestModelServiceUpdate).
"""

import importlib

_serializers = importlib.import_module("app.services.model-management.serializers")

_redact_inference_endpoint = _serializers._redact_inference_endpoint
REDACTED_VALUE = _serializers.REDACTED_VALUE


def test_redacts_api_key_value_when_present():
    raw = {
        "callbackUrl": "http://example.com/infer",
        "inferenceApiKey": {"name": "Authorization", "value": "super-secret-token"},
    }
    out = _redact_inference_endpoint(raw)
    assert out["inferenceApiKey"]["value"] == REDACTED_VALUE
    assert out["inferenceApiKey"]["name"] == "Authorization"
    # callbackUrl and every other key pass through untouched.
    assert out["callbackUrl"] == "http://example.com/infer"


def test_does_not_mutate_the_input_dict():
    raw = {"inferenceApiKey": {"name": "Authorization", "value": "super-secret-token"}}
    _redact_inference_endpoint(raw)
    assert raw["inferenceApiKey"]["value"] == "super-secret-token"


def test_no_inference_api_key_passes_through_unchanged():
    raw = {"callbackUrl": "http://example.com/infer", "schema": {}}
    out = _redact_inference_endpoint(raw)
    assert out == raw


def test_inference_api_key_without_value_untouched():
    raw = {"inferenceApiKey": {"name": "Authorization"}}
    out = _redact_inference_endpoint(raw)
    assert "value" not in out["inferenceApiKey"]


def test_none_input_returns_none():
    assert _redact_inference_endpoint(None) is None


def test_non_dict_input_passed_through():
    assert _redact_inference_endpoint("not-a-dict") == "not-a-dict"
