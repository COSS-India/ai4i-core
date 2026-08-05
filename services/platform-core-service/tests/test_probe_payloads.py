"""Unit tests for app/utils/probe_payloads.py.

Covers the _PRESERVE_VERBATIM_KEYS fix: identifier-like fields (model,
deployment, engine, ...) in a model card's schema.request must be sent
verbatim in the probe payload, not overwritten with a generic placeholder —
discovered against a real OpenAI-compatible vLLM deployment that 404s on
an unrecognized "model" value (see AI4IDS-1844 follow-up).
"""

from app.utils.probe_payloads import (
    build_probe_payload,
    build_ulca_payload,
    get_expected_response_shape,
)


class TestPreserveVerbatimKeys:
    def test_model_field_is_preserved_not_replaced_with_test(self):
        request_schema = {
            "model": "google/gemma-4-31B-it",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        payload = build_ulca_payload("llm", request_schema)
        assert payload["model"] == "google/gemma-4-31B-it"

    def test_messages_list_passes_through_unchanged(self):
        """Pre-existing behavior, unaffected by this fix: non-empty lists
        are passed through verbatim regardless of key name."""
        request_schema = {
            "model": "google/gemma-4-31B-it",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        payload = build_ulca_payload("llm", request_schema)
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]

    def test_generic_free_text_string_field_is_still_replaced(self):
        """Regression guard: genuine free-text fields (not identifiers)
        must still get the generic placeholder — only identifier-like keys
        are exempted."""
        request_schema = {"prompt": "a real sample prompt", "sourceLanguage": "en"}
        payload = build_ulca_payload("llm", request_schema)
        assert payload["prompt"] == "test"
        assert payload["sourceLanguage"] == "test"

    def test_preserve_key_matching_is_case_and_separator_insensitive(self):
        for key in ["model", "Model", "MODEL", "model_name", "modelName", "model-id", "deploymentName", "ENGINE_ID"]:
            payload = build_ulca_payload("llm", {key: "real-value-should-survive"})
            assert payload[key] == "real-value-should-survive", key

    def test_non_identifier_key_containing_model_substring_not_over_matched(self):
        """Sanity check: the normalization is exact-match against a known
        set of identifier key names, not a loose substring match — a field
        like "modelDescription" (free text) must still be substituted."""
        payload = build_ulca_payload("llm", {"modelDescription": "a long description"})
        assert payload["modelDescription"] == "test"

    def test_dict_and_non_empty_list_values_unaffected_by_the_fix(self):
        """The fix only touches top-level string values — dict/list values
        were already passed through verbatim before this change."""
        request_schema = {
            "model": "google/gemma-4-31B-it",
            "config": {"temperature": 1.0},
            "stop": ["</s>"],
        }
        payload = build_ulca_payload("llm", request_schema)
        assert payload["config"] == {"temperature": 1.0}
        assert payload["stop"] == ["</s>"]

    def test_end_to_end_via_build_probe_payload(self):
        request_schema = {
            "model": "google/gemma-4-31B-it",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        payload, kind = build_probe_payload("llm", request_schema, triton_schema=None)
        assert kind == "ulca"
        assert payload["model"] == "google/gemma-4-31B-it"


class TestBuildUlcaPayloadFallbacks:
    def test_no_request_schema_uses_task_type_dummy(self):
        payload = build_ulca_payload("asr", None)
        assert payload == {
            "audio": [{"audioContent": ""}],
            "config": {"language": {"sourceLanguage": "en"}},
        }

    def test_unknown_task_type_with_no_schema_uses_generic_fallback(self):
        payload = build_ulca_payload("some-unregistered-task-type", None)
        assert payload == {"input": [{"source": "test"}]}

    def test_empty_request_schema_dict_falls_back_to_dummy(self):
        """An empty dict is falsy, so it must not short-circuit into an
        empty payload — falls through to the task-type dummy."""
        payload = build_ulca_payload("asr", {})
        assert payload == {
            "audio": [{"audioContent": ""}],
            "config": {"language": {"sourceLanguage": "en"}},
        }


class TestGetExpectedResponseShape:
    def test_llm_default_is_openai_chat_completions_shaped_not_ulca(self):
        """Real-world LLM deployments (vLLM/TGI/OpenAI/...) are
        overwhelmingly OpenAI chat-completions-shaped, not ULCA-wrapped —
        the default must reflect the common case, not the ULCA exception
        (AI4IDS-1844 follow-up: a real vLLM deployment returning
        {"choices": [{"message": {"content": "..."}}]})."""
        shape = get_expected_response_shape("llm")
        assert shape == {"choices": [{"message": {"content": "sample generated text"}}]}
        assert "output" not in shape

    def test_other_task_types_still_use_the_ulca_envelope(self):
        """Regression guard: only "llm" changed — every other task type
        keeps its ULCA output/target (or audio) envelope."""
        assert get_expected_response_shape("nmt") == {
            "output": [{"target": "sample translated text"}]
        }
        assert get_expected_response_shape("asr") == {
            "output": [{"source": "sample transcript"}]
        }
        assert get_expected_response_shape("tts") == {
            "audio": [{"audioContent": "sample-base64-audio"}]
        }

    def test_unknown_task_type_returns_none(self):
        assert get_expected_response_shape("speaker-diarization") is None
        assert get_expected_response_shape("not-a-real-task-type") is None

    def test_none_task_type_returns_none(self):
        assert get_expected_response_shape(None) is None

    def test_is_case_insensitive(self):
        assert get_expected_response_shape("LLM") == get_expected_response_shape("llm")


class TestAdapterConfigModelNameOverride:
    """adapterConfig.model_name (from the model card's InferenceEndpoint
    column) is the authoritative real model identifier for LLM deployments
    — schema.request.model is only a sample the admin typed in and has
    repeatedly been found stale/wrong in practice (AI4IDS-1844 follow-up:
    a real vLLM deployment configured with schema.request.model =
    "google/gemma-5-E4B-it" while the actually-loaded model was
    "google/gemma-4-31B-it", 404ing every probe until corrected). An
    upcoming model-schema change may drop "model" from schema.request
    entirely, so this can't just be a fallback for when schema.request
    happens to be silent — it must always win when supplied."""

    def test_model_name_overrides_a_stale_schema_request_model(self):
        request_schema = {
            "model": "google/gemma-5-E4B-it",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        payload = build_ulca_payload("llm", request_schema, model_name="google/gemma-4-31B-it")
        assert payload["model"] == "google/gemma-4-31B-it"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]

    def test_alternate_spelling_key_is_overwritten_in_place_not_duplicated(self):
        """PR review: a card that declares "modelName" (one of the nine
        _PRESERVE_VERBATIM_KEYS spellings) instead of "model" must have
        THAT key overwritten — not keep its stale value while also gaining
        a brand-new literal "model" key, which would send two conflicting
        identifiers and leave the wrong one in the payload."""
        request_schema = {
            "modelName": "google/gemma-5-E4B-it",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        payload = build_ulca_payload("llm", request_schema, model_name="google/gemma-4-31B-it")
        assert payload["modelName"] == "google/gemma-4-31B-it"
        assert "model" not in payload

    def test_deployment_spelling_key_is_overwritten_in_place(self):
        request_schema = {"deployment": "stale-deployment-name", "messages": []}
        payload = build_ulca_payload("llm", request_schema, model_name="google/gemma-4-31B-it")
        assert payload["deployment"] == "google/gemma-4-31B-it"
        assert "model" not in payload

    def test_model_name_is_added_even_when_request_schema_has_no_model_key(self):
        """Forward-compatibility with the upcoming schema change: even if
        schema.request never declared "model" at all, the probe must still
        carry the real model name."""
        request_schema = {"messages": [{"role": "user", "content": "Hello"}]}
        payload = build_ulca_payload("llm", request_schema, model_name="google/gemma-4-31B-it")
        assert payload["model"] == "google/gemma-4-31B-it"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]

    def test_model_name_used_as_the_whole_fallback_when_no_request_schema_at_all(self):
        """No request_schema and no "model" key anywhere — but we still
        know the real model name, so build an OpenAI-shaped payload
        instead of falling through to the generic ULCA dummy (which has no
        "model"/"messages" contract and would never succeed against a real
        OpenAI-compatible server)."""
        payload = build_ulca_payload("llm", None, model_name="google/gemma-4-31B-it")
        assert payload == {
            "model": "google/gemma-4-31B-it",
            "messages": [{"role": "user", "content": "Hello"}],
        }

    def test_no_model_name_falls_back_to_prior_behavior(self):
        """model_name omitted entirely — existing _PRESERVE_VERBATIM_KEYS
        behavior is unaffected (no regression for models without
        adapterConfig.model_name configured)."""
        request_schema = {
            "model": "google/gemma-5-E4B-it",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        payload = build_ulca_payload("llm", request_schema, model_name=None)
        assert payload["model"] == "google/gemma-5-E4B-it"

        payload_no_schema = build_ulca_payload("llm", None, model_name=None)
        assert payload_no_schema == {"messages": [{"role": "user", "content": "Hello"}]}

    def test_model_name_ignored_for_non_llm_task_types(self):
        """The override is an LLM/OpenAI-specific concept — must not leak
        a "model" field into a translation/ASR/etc. probe payload that
        never had one."""
        payload = build_ulca_payload(
            "asr", {"audio": [{"audioContent": ""}]}, model_name="google/gemma-4-31B-it"
        )
        assert "model" not in payload

        payload_no_schema = build_ulca_payload("asr", None, model_name="google/gemma-4-31B-it")
        assert payload_no_schema == {
            "audio": [{"audioContent": ""}],
            "config": {"language": {"sourceLanguage": "en"}},
        }

    def test_end_to_end_via_build_probe_payload(self):
        request_schema = {
            "model": "google/gemma-5-E4B-it",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        payload, kind = build_probe_payload(
            "llm", request_schema, triton_schema=None, model_name="google/gemma-4-31B-it"
        )
        assert kind == "ulca"
        assert payload["model"] == "google/gemma-4-31B-it"
