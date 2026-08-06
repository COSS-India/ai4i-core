"""Unit tests for app/utils/endpoint_validator.py (AI4IDS-1844).

Covers:
- validate_response_shape: structural matching of a live response against
  an admin-supplied sample schema.
- test_inference (sync probe): reachability + response-shape gating.
- test_inference_async (poll-until-done probe): submit/poll dispatch,
  success after N polls, and the bounded-wait timeout path.
- validate_endpoint orchestrator: end-to-end is_valid outcome for each case.
"""

import asyncio
import time

import pytest

from app.utils import endpoint_validator as ev
from app.utils.endpoint_validator import (
    ValidationStatus,
    validate_endpoint,
    validate_response_shape,
)


# ── Fakes for httpx.AsyncClient ──────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, json_body=None, text: str = ""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text

    def json(self):
        if self._json_body is None:
            raise ValueError("response body is not valid JSON")
        return self._json_body


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient: returns queued responses in order,
    one per `.post()` call, regardless of URL."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.post_calls = []  # list of URLs, in order
        self.post_bodies = []  # list of json bodies, in order

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        self.post_calls.append(url)
        self.post_bodies.append(json)
        return self._responses.pop(0)


class _RaisingAsyncClient:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        raise self._exc


class _AssertNeverCalledAsyncClient:
    """Used to prove a code path never constructs/uses an HTTP client at
    all — e.g. an SSRF-blocked host must short-circuit before any request."""

    async def __aenter__(self):
        raise AssertionError("no HTTP client should have been constructed")

    async def __aexit__(self, *_exc):
        return False

    async def post(self, *_args, **_kwargs):
        raise AssertionError("no HTTP request should have been made")


def _patch_client(monkeypatch, client) -> None:
    monkeypatch.setattr(ev.httpx, "AsyncClient", lambda **_kwargs: client)


# ── validate_response_shape ──────────────────────────────────────────────────


class TestValidateResponseShape:
    def test_exact_match_passes(self):
        expected = {"output": [{"source": "hi", "target": "namaste"}]}
        actual = {"output": [{"source": "hello", "target": "namaskara"}]}
        result = validate_response_shape(actual, expected)
        assert result.status == ValidationStatus.PASSED

    def test_missing_key_fails(self):
        expected = {"output": [{"source": "hi", "target": "namaste"}]}
        actual = {"output": [{"source": "hello"}]}
        result = validate_response_shape(actual, expected)
        assert result.status == ValidationStatus.FAILED
        assert "target" in result.message

    def test_wrong_type_fails(self):
        expected = {"audio": [{"audioContent": "base64=="}]}
        actual = {"audio": [{"audioContent": 12345}]}
        result = validate_response_shape(actual, expected)
        assert result.status == ValidationStatus.FAILED
        assert "expected string" in result.message

    def test_expected_non_empty_array_but_actual_empty_fails(self):
        expected = {"output": [{"source": "hi"}]}
        actual = {"output": []}
        result = validate_response_shape(actual, expected)
        assert result.status == ValidationStatus.FAILED
        assert "non-empty array" in result.message

    def test_top_level_not_object_fails(self):
        expected = {"output": [{"source": "hi"}]}
        result = validate_response_shape(["not", "an", "object"], expected)
        assert result.status == ValidationStatus.FAILED

    def test_extra_actual_keys_are_ignored(self):
        """Only keys present in the sample schema are checked — the real
        response is allowed to have additional fields."""
        expected = {"output": [{"source": "hi"}]}
        actual = {"output": [{"source": "hello", "confidence": 0.98}], "requestId": "abc"}
        result = validate_response_shape(actual, expected)
        assert result.status == ValidationStatus.PASSED


# ── test_inference (sync probe) ──────────────────────────────────────────────


class TestTestInferenceSync:
    @pytest.mark.asyncio
    async def test_reachable_returns_parsed_body(self, monkeypatch):
        _patch_client(
            monkeypatch,
            _FakeAsyncClient([_FakeResponse(200, json_body={"output": [{"source": "x"}]})]),
        )
        detail, body, kind = await ev.test_inference(
            endpoint="http://model.example.com/infer", task_type="asr"
        )
        assert detail.status == ValidationStatus.PASSED
        assert body == {"output": [{"source": "x"}]}
        assert kind == "ulca"

    @pytest.mark.asyncio
    async def test_triton_schema_reports_triton_v2_kind(self, monkeypatch):
        """build_probe_payload switches to a Triton V2 payload whenever the
        model card carries schema.response.triton — the caller (orchestrator)
        needs this to know a ULCA default shape must never apply."""
        _patch_client(
            monkeypatch,
            _FakeAsyncClient(
                [_FakeResponse(200, json_body={"model_name": "m", "outputs": []})]
            ),
        )
        detail, body, kind = await ev.test_inference(
            endpoint="http://model.example.com/infer",
            task_type="asr",
            triton_schema={"inputs": [{"name": "AUDIO", "datatype": "BYTES", "shape": [1]}]},
        )
        assert detail.status == ValidationStatus.PASSED
        assert kind == "triton_v2"

    @pytest.mark.asyncio
    async def test_5xx_fails_without_body(self, monkeypatch):
        _patch_client(monkeypatch, _FakeAsyncClient([_FakeResponse(503, text="down")]))
        detail, body, kind = await ev.test_inference(
            endpoint="http://model.example.com/infer", task_type="asr"
        )
        assert detail.status == ValidationStatus.FAILED
        assert body is None

    @pytest.mark.asyncio
    async def test_connect_error_produces_clear_message(self, monkeypatch):
        import httpx

        _patch_client(monkeypatch, _RaisingAsyncClient(httpx.ConnectError("refused")))
        detail, body, kind = await ev.test_inference(
            endpoint="http://unreachable.example.com/infer", task_type="asr"
        )
        assert detail.status == ValidationStatus.FAILED
        assert "Could not connect" in detail.message
        assert body is None

    @pytest.mark.asyncio
    async def test_timeout_produces_clear_message(self, monkeypatch):
        import httpx

        _patch_client(monkeypatch, _RaisingAsyncClient(httpx.TimeoutException("slow")))
        detail, body, kind = await ev.test_inference(
            endpoint="http://slow.example.com/infer", task_type="asr", timeout=5.0
        )
        assert detail.status == ValidationStatus.FAILED
        assert "timed out" in detail.message
        assert body is None


# ── test_inference_async (poll-until-done probe) ─────────────────────────────


class TestTestInferenceAsync:
    @pytest.mark.asyncio
    async def test_completes_after_polling(self, monkeypatch):
        _patch_client(
            monkeypatch,
            _FakeAsyncClient(
                [
                    _FakeResponse(200, json_body={"requestId": "job-1"}),  # submit
                    _FakeResponse(202),  # poll 1: still processing
                    _FakeResponse(202),  # poll 2: still processing
                    _FakeResponse(200, json_body={"output": [{"source": "done"}]}),  # poll 3: done
                ]
            ),
        )
        detail, body, kind = await ev.test_inference_async(
            endpoint="http://model.example.com/submit",
            polling_url="http://model.example.com/poll",
            poll_interval_ms=10,
            task_type="asr",
            max_poll_attempts=10,
            max_poll_wait_seconds=5.0,
        )
        assert detail.status == ValidationStatus.PASSED
        assert body == {"output": [{"source": "done"}]}

    @pytest.mark.asyncio
    async def test_submit_5xx_fails_immediately(self, monkeypatch):
        _patch_client(monkeypatch, _FakeAsyncClient([_FakeResponse(500)]))
        detail, body, kind = await ev.test_inference_async(
            endpoint="http://model.example.com/submit",
            polling_url="http://model.example.com/poll",
            poll_interval_ms=10,
            task_type="asr",
        )
        assert detail.status == ValidationStatus.FAILED
        assert "submit" in detail.message
        assert body is None

    @pytest.mark.asyncio
    async def test_poll_connect_error_names_polling_url_not_submit_endpoint(self, monkeypatch):
        """PR review: a ConnectError on the POLL call must name polling_url
        in the message, not endpoint (the submit URL) — they can be
        different hosts, and misattributing this makes the error
        misleading for whoever's debugging it."""

        class _FailOnPollClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def post(self, url, json=None, headers=None, timeout=None):
                if "submit" in url:
                    return _FakeResponse(200, json_body={"requestId": "job-1"})
                import httpx

                raise httpx.ConnectError("refused")

        _patch_client(monkeypatch, _FailOnPollClient())

        detail, body, kind = await ev.test_inference_async(
            endpoint="http://model.example.com/submit",
            polling_url="http://poll-host.example.com/poll",
            poll_interval_ms=10,
            task_type="asr",
        )

        assert detail.status == ValidationStatus.FAILED
        assert "poll-host.example.com" in detail.message
        assert "model.example.com/submit" not in detail.message
        assert body is None

    @pytest.mark.asyncio
    async def test_poll_failure_status_fails(self, monkeypatch):
        _patch_client(
            monkeypatch,
            _FakeAsyncClient(
                [
                    _FakeResponse(200, json_body={"requestId": "job-1"}),
                    _FakeResponse(400),  # poll fails outright (not 202/200)
                ]
            ),
        )
        detail, body, kind = await ev.test_inference_async(
            endpoint="http://model.example.com/submit",
            polling_url="http://model.example.com/poll",
            poll_interval_ms=10,
            task_type="asr",
        )
        assert detail.status == ValidationStatus.FAILED
        assert body is None

    @pytest.mark.asyncio
    async def test_never_completes_times_out(self, monkeypatch):
        """An endpoint that always says 202 must not hang forever — the poll
        budget (attempts and wall-clock) bounds the wait."""
        responses = [_FakeResponse(200, json_body={"requestId": "job-1"})]
        responses += [_FakeResponse(202) for _ in range(20)]
        _patch_client(monkeypatch, _FakeAsyncClient(responses))

        detail, body, kind = await ev.test_inference_async(
            endpoint="http://model.example.com/submit",
            polling_url="http://model.example.com/poll",
            poll_interval_ms=100,
            task_type="asr",
            max_poll_attempts=10,
            max_poll_wait_seconds=0.2,
        )
        assert detail.status == ValidationStatus.FAILED
        assert "did not complete" in detail.message
        assert body is None


# ── validate_endpoint orchestrator ──────────────────────────────────────────


class TestValidateEndpointOrchestrator:
    @pytest.mark.asyncio
    async def test_sync_endpoint_valid_response_shape_is_valid(self, monkeypatch):
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient([_FakeResponse(200, json_body={"output": [{"source": "x"}]})]),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="asr",
            expected_response_schema={"output": [{"source": "hi"}]},
        )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_sync_endpoint_wrong_response_shape_is_invalid(self, monkeypatch):
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient([_FakeResponse(200, json_body={"unexpected": "field"})]),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="asr",
            expected_response_schema={"output": [{"source": "hi"}]},
        )
        assert result.is_valid is False
        shape_details = [d for d in result.details if d.level == ev.ValidationLevel.RESPONSE_SHAPE]
        assert shape_details and shape_details[0].status == ValidationStatus.FAILED

    @pytest.mark.asyncio
    async def test_unreachable_endpoint_is_invalid_and_never_checks_shape(self, monkeypatch):
        import httpx

        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(monkeypatch, _RaisingAsyncClient(httpx.ConnectError("refused")))
        result = await validate_endpoint(
            endpoint="http://unreachable.example.com/infer",
            task_type="asr",
            expected_response_schema={"output": [{"source": "hi"}]},
        )
        assert result.is_valid is False
        assert not any(d.level == ev.ValidationLevel.RESPONSE_SHAPE for d in result.details)

    @pytest.mark.asyncio
    async def test_async_model_dispatches_to_polling(self, monkeypatch):
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient(
                [
                    _FakeResponse(200, json_body={"requestId": "job-1"}),
                    _FakeResponse(200, json_body={"output": [{"source": "done"}]}),
                ]
            ),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/submit",
            task_type="asr",
            expected_response_schema={"output": [{"source": "hi"}]},
            is_sync_api=False,
            polling_url="http://model.example.com/poll",
            poll_interval_ms=10,
        )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_ssrf_blocked_host_is_invalid(self, monkeypatch):
        monkeypatch.setattr(ev, "is_safe_host", _async_false)
        result = await validate_endpoint(
            endpoint="http://169.254.169.254/infer",
            task_type="asr",
            expected_response_schema={"output": [{"source": "hi"}]},
        )
        assert result.is_valid is False


# ── Polling-URL SSRF guard (PR review: was bypassable via the poll channel) ─


class TestPollingUrlSsrfGuard:
    @pytest.mark.asyncio
    async def test_internal_polling_url_is_blocked_before_any_request(self, monkeypatch):
        """A model card with a safe public endpoint but an internal
        pollingUrl must not let platform-core issue an internal POST — the
        polling host gets the same SSRF check as the main endpoint, and
        _AssertNeverCalledAsyncClient proves no HTTP client is even
        constructed once it's blocked."""

        async def _safe_except_polling_host(hostname):
            return hostname != "169.254.169.254"

        monkeypatch.setattr(ev, "is_safe_host", _safe_except_polling_host)
        _patch_client(monkeypatch, _AssertNeverCalledAsyncClient())

        result = await validate_endpoint(
            endpoint="http://model.example.com/submit",
            task_type="asr",
            expected_response_schema={"output": [{"source": "hi"}]},
            is_sync_api=False,
            polling_url="http://169.254.169.254/poll",
            poll_interval_ms=10,
        )

        assert result.is_valid is False
        blocked = [d for d in result.details if "Polling endpoint host is not allowed" in d.message]
        assert blocked, [d.message for d in result.details]

    @pytest.mark.asyncio
    async def test_polled_status_is_never_leaked_when_polling_host_is_blocked(self, monkeypatch):
        """The failure must come from the SSRF check itself, not from
        actually polling the internal host and echoing its response status
        back to the caller (the second half of the review comment: this
        must not become a reachability/status oracle for internal hosts)."""

        async def _safe_except_polling_host(hostname):
            return hostname != "internal.example"

        monkeypatch.setattr(ev, "is_safe_host", _safe_except_polling_host)
        _patch_client(monkeypatch, _AssertNeverCalledAsyncClient())

        result = await validate_endpoint(
            endpoint="http://model.example.com/submit",
            task_type="asr",
            expected_response_schema={"output": [{"source": "hi"}]},
            is_sync_api=False,
            polling_url="http://internal.example/poll",
            poll_interval_ms=10,
        )

        assert result.is_valid is False
        assert not any("returned HTTP" in d.message for d in result.details)

    @pytest.mark.asyncio
    async def test_safe_polling_url_is_unaffected(self, monkeypatch):
        """Sanity check: the new check doesn't block a legitimately public
        pollingUrl — same as before this fix."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient(
                [
                    _FakeResponse(200, json_body={"requestId": "job-1"}),
                    _FakeResponse(200, json_body={"output": [{"source": "done"}]}),
                ]
            ),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/submit",
            task_type="asr",
            expected_response_schema={"output": [{"source": "hi"}]},
            is_sync_api=False,
            polling_url="http://model.example.com/poll",
            poll_interval_ms=10,
        )
        assert result.is_valid is True


# ── Task-type default response shape (PR review: shape is a function of ──
# ── task_type, not a mandatory per-service admin input) ─────────────────


class TestTaskTypeDefaultShape:
    @pytest.mark.asyncio
    async def test_default_shape_applied_when_none_supplied(self, monkeypatch):
        """No expected_response_schema passed at all — validate_endpoint
        still checks the built-in ASR default."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient([_FakeResponse(200, json_body={"nothing": "useful"})]),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="asr",
        )
        assert result.is_valid is False
        shape_details = [d for d in result.details if d.level == ev.ValidationLevel.RESPONSE_SHAPE]
        assert shape_details and shape_details[0].status == ValidationStatus.FAILED

    @pytest.mark.asyncio
    async def test_default_shape_passes_for_conformant_response(self, monkeypatch):
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient([_FakeResponse(200, json_body={"output": [{"source": "hello"}]})]),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="asr",
        )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_llm_default_matches_a_real_openai_style_chat_completion(self, monkeypatch):
        """The llm default is OpenAI chat-completions-shaped, not ULCA —
        a real vLLM/OpenAI-compatible response (with plenty of extra
        fields the shape matcher must ignore) should pass with NO
        expectedResponseSchema supplied at all."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        real_vllm_response = {
            "id": "chatcmpl-887eb644ca6e8de9",
            "object": "chat.completion",
            "created": 1785927105,
            "model": "google/gemma-4-31B-it",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello! How can I help you today?",
                        "refusal": None,
                    },
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 14, "total_tokens": 24, "completion_tokens": 10},
        }
        _patch_client(monkeypatch, _FakeAsyncClient([_FakeResponse(200, json_body=real_vllm_response)]))
        result = await validate_endpoint(
            endpoint="http://model.example.com",
            task_type="llm",
        )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_llm_default_rejects_a_ulca_shaped_response(self, monkeypatch):
        """Inverse of the above: a ULCA-shaped {"output": [...]}"} response
        (the OLD default) must now FAIL against the llm default, since a
        conformant response no longer looks like that."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient([_FakeResponse(200, json_body={"output": [{"target": "hi"}]})]),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="llm",
        )
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_model_name_from_adapter_config_reaches_the_actual_probe_body(self, monkeypatch):
        """End-to-end: validate_endpoint's model_name param (sourced from
        the model card's adapterConfig.model_name) must land in the real
        outgoing request body's "model" field, overriding a stale
        schema.request.model sample — the exact AI4IDS-1844 follow-up bug."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        client = _FakeAsyncClient(
            [_FakeResponse(200, json_body={"choices": [{"message": {"content": "hi"}}]})]
        )
        _patch_client(monkeypatch, client)

        result = await validate_endpoint(
            endpoint="http://model.example.com",
            task_type="llm",
            request_schema={
                "model": "google/gemma-5-E4B-it",  # stale sample
                "messages": [{"role": "user", "content": "Hello"}],
            },
            model_name="google/gemma-4-31B-it",  # authoritative
        )

        assert result.is_valid is True
        assert client.post_bodies[0]["model"] == "google/gemma-4-31B-it"

    @pytest.mark.asyncio
    async def test_explicit_override_wins_over_default(self, monkeypatch):
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient([_FakeResponse(200, json_body={"custom": [{"field": "x"}]})]),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="asr",
            expected_response_schema={"custom": [{"field": "sample"}]},
        )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_unknown_task_type_skips_shape_check_entirely(self, monkeypatch):
        """No built-in default for this task type and no override supplied
        — the shape check is skipped, not guessed; reachability alone
        determines validity."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient([_FakeResponse(200, json_body={"anything": "goes"})]),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="speaker-diarization",
        )
        assert result.is_valid is True
        assert not any(d.level == ev.ValidationLevel.RESPONSE_SHAPE for d in result.details)

    @pytest.mark.asyncio
    async def test_triton_backed_service_skips_ulca_default_shape(self, monkeypatch):
        """PR review regression: build_probe_payload sends a Triton V2
        payload whenever triton_schema is set (inferenceServerType
        defaults to "triton"), and a real Triton server answers with
        {"model_name": ..., "outputs": [...]} — no "output" key at all.
        The ULCA default must NOT apply here, or every Triton-backed
        service without a hand-supplied schema would fail creation."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient(
                [_FakeResponse(200, json_body={"model_name": "asr-model", "outputs": []})]
            ),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="asr",
            triton_schema={"inputs": [{"name": "AUDIO", "datatype": "BYTES", "shape": [1]}]},
            # expected_response_schema intentionally omitted, like a
            # pre-existing service / the bulk endpoint-update path.
        )
        assert result.is_valid is True
        assert not any(d.level == ev.ValidationLevel.RESPONSE_SHAPE for d in result.details)

    @pytest.mark.asyncio
    async def test_triton_backed_service_still_honors_explicit_override(self, monkeypatch):
        """An admin-supplied expected_response_schema still applies even
        for a Triton-backed probe — only the built-in ULCA *default* is
        gated on payload_kind, not an explicit override."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient(
                [_FakeResponse(200, json_body={"model_name": "asr-model", "outputs": []})]
            ),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/infer",
            task_type="asr",
            triton_schema={"inputs": [{"name": "AUDIO", "datatype": "BYTES", "shape": [1]}]},
            expected_response_schema={"model_name": "sample", "outputs": []},
        )
        assert result.is_valid is True
        shape_details = [d for d in result.details if d.level == ev.ValidationLevel.RESPONSE_SHAPE]
        assert shape_details and shape_details[0].status == ValidationStatus.PASSED

    @pytest.mark.asyncio
    async def test_triton_backed_async_service_also_skips_ulca_default(self, monkeypatch):
        """Same gating must apply on the async/polling path, not just sync."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(
            monkeypatch,
            _FakeAsyncClient(
                [
                    _FakeResponse(200, json_body={"requestId": "job-1"}),
                    _FakeResponse(200, json_body={"model_name": "asr-model", "outputs": []}),
                ]
            ),
        )
        result = await validate_endpoint(
            endpoint="http://model.example.com/submit",
            task_type="asr",
            triton_schema={"inputs": [{"name": "AUDIO", "datatype": "BYTES", "shape": [1]}]},
            is_sync_api=False,
            polling_url="http://model.example.com/poll",
            poll_interval_ms=10,
        )
        assert result.is_valid is True
        assert not any(d.level == ev.ValidationLevel.RESPONSE_SHAPE for d in result.details)


# ── Async poll wall-clock bound (PR review: only sleep time was bounded) ────


class _SlowPollAsyncClient:
    """Each poll call blocks for `delay_s` unless the caller passes a
    shorter timeout, in which case it raises like httpx would when a
    request exceeds its own timeout — used to prove each poll's own
    per-call timeout is capped to the remaining wall-clock budget."""

    def __init__(self, delay_s: float, submit_body: dict):
        self._delay_s = delay_s
        self._submit_body = submit_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        if "submit" in url:
            return _FakeResponse(200, json_body=self._submit_body)
        if timeout is not None and timeout < self._delay_s:
            import httpx

            raise httpx.TimeoutException("simulated slow poll exceeded its budget")
        await asyncio.sleep(0)
        return _FakeResponse(202)


class TestAsyncPollWallClockBound:
    @pytest.mark.asyncio
    async def test_per_call_timeout_is_capped_to_remaining_budget(self, monkeypatch):
        """Regression: previously only sleep time counted toward
        max_poll_wait_seconds, so a poll endpoint whose individual HTTP
        calls hang could hold the request for roughly
        (max_poll_attempts * timeout) regardless of the configured budget.
        Each poll's own request timeout must be capped to whatever's left
        of max_poll_wait_seconds, so a call that would take longer than the
        remaining budget fails fast instead of hanging the whole probe."""
        _patch_client(
            monkeypatch,
            _SlowPollAsyncClient(delay_s=5.0, submit_body={"requestId": "job-1"}),
        )
        start = time.monotonic()
        detail, body, kind = await ev.test_inference_async(
            endpoint="http://model.example.com/submit",
            polling_url="http://model.example.com/poll",
            poll_interval_ms=10,
            task_type="asr",
            timeout=15.0,
            max_poll_attempts=10,
            max_poll_wait_seconds=0.5,
        )
        elapsed = time.monotonic() - start

        assert detail.status == ValidationStatus.FAILED
        assert body is None
        # Must return close to the 0.5s budget — well under the 5s
        # simulated per-call delay, and nowhere near the old bug's worst
        # case of max_poll_attempts * timeout (~150s with these defaults).
        assert elapsed < 3.0


# ── LLM-only endpoint path auto-append ──────────────────────────────────────
# For taskType "llm" the admin supplies just host:port, not the inference
# path — the live probe must attach /v1/chat/completions internally.
# Every other task type's endpoint is used exactly as given.


class TestResolveProbeEndpoint:
    def test_llm_host_port_gets_path_appended(self):
        assert (
            ev._resolve_probe_endpoint("http://model.example.com:8080", "llm")
            == "http://model.example.com:8080/v1/chat/completions"
        )

    def test_llm_trailing_slash_does_not_produce_double_slash(self):
        assert (
            ev._resolve_probe_endpoint("http://model.example.com:8080/", "llm")
            == "http://model.example.com:8080/v1/chat/completions"
        )

    def test_endpoint_already_carrying_the_path_gets_double_appended(self):
        """PR review: this function mirrors inference-service's
        LlmService.resolve_upstream_url exactly (base.rstrip('/') + path,
        unconditionally) — it must NOT guard against *endpoint* already
        carrying the path. Rejecting that misconfiguration up front is
        _llm_endpoint_has_extra_path's job (see TestLlmEndpointExtraPath
        below), not this function's — silently correcting it here would
        make a broken stored config validate green and only fail later in
        production, where the real upstream-URL builder double-appends the
        same way."""
        endpoint = "http://model.example.com:8080/v1/chat/completions"
        assert (
            ev._resolve_probe_endpoint(endpoint, "llm")
            == "http://model.example.com:8080/v1/chat/completions/v1/chat/completions"
        )

    def test_non_llm_task_types_are_never_modified(self):
        endpoint = "http://model.example.com:9000"
        for task_type in ["asr", "nmt", "tts", "ocr", "ner", None]:
            assert ev._resolve_probe_endpoint(endpoint, task_type) == endpoint


# ── _llm_endpoint_has_extra_path: reject a stored path instead of silently
# accepting it (PR review) — a service configured with endpoint already
# including /v1/chat/completions would double-append and 404 at real
# inference time, since inference-service's LlmService.resolve_upstream_url
# builds the upstream the same unconditional way.


class TestLlmEndpointExtraPath:
    def test_endpoint_with_the_path_is_rejected(self):
        detail = ev._llm_endpoint_has_extra_path(
            "http://model.example.com:8080/v1/chat/completions", "llm"
        )
        assert detail is not None
        assert detail.status == ValidationStatus.FAILED
        assert "host:port only" in detail.message

    def test_endpoint_with_the_path_and_trailing_slash_is_rejected(self):
        detail = ev._llm_endpoint_has_extra_path(
            "http://model.example.com:8080/v1/chat/completions/", "llm"
        )
        assert detail is not None
        assert detail.status == ValidationStatus.FAILED

    def test_bare_host_port_is_not_rejected(self):
        assert ev._llm_endpoint_has_extra_path("http://model.example.com:8080", "llm") is None

    def test_non_llm_task_type_is_never_rejected_even_with_the_same_path(self):
        """The path is only meaningful for llm — a non-llm service that
        happens to end in /v1/chat/completions is nobody's business here."""
        detail = ev._llm_endpoint_has_extra_path(
            "http://model.example.com:8080/v1/chat/completions", "asr"
        )
        assert detail is None

    @pytest.mark.asyncio
    async def test_validate_endpoint_rejects_it_without_any_network_call(self, monkeypatch):
        """End-to-end: must fail fast, before constructing any HTTP client
        — proven via a client double that raises if touched at all."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        _patch_client(monkeypatch, _AssertNeverCalledAsyncClient())

        result = await validate_endpoint(
            endpoint="http://model.example.com:8080/v1/chat/completions",
            task_type="llm",
        )

        assert result.is_valid is False
        assert any("host:port only" in d.message for d in result.details)


class TestLlmEndpointAutoAppendEndToEnd:
    @pytest.mark.asyncio
    async def test_bare_host_port_probe_actually_hits_the_appended_path(self, monkeypatch):
        """End-to-end: validate_endpoint must POST to the appended path,
        not the bare host:port the admin actually supplied."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        client = _FakeAsyncClient(
            [_FakeResponse(200, json_body={"choices": [{"message": {"content": "hi"}}]})]
        )
        _patch_client(monkeypatch, client)

        result = await validate_endpoint(
            endpoint="http://model.example.com:8080",
            task_type="llm",
        )

        assert result.is_valid is True
        assert client.post_calls == ["http://model.example.com:8080/v1/chat/completions"]

    @pytest.mark.asyncio
    async def test_non_llm_bare_host_port_is_posted_to_unmodified(self, monkeypatch):
        """Regression guard: this is an llm-only convenience — every other
        task type's endpoint must be hit exactly as configured, even if it
        also happens to be a bare host:port with no path."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        client = _FakeAsyncClient([_FakeResponse(200, json_body={"output": [{"source": "hi"}]})])
        _patch_client(monkeypatch, client)

        result = await validate_endpoint(
            endpoint="http://model.example.com:8080",
            task_type="asr",
        )

        assert result.is_valid is True
        assert client.post_calls == ["http://model.example.com:8080"]

    @pytest.mark.asyncio
    async def test_async_llm_submit_call_also_gets_the_path_appended(self, monkeypatch):
        """The same auto-append applies to the async (poll-until-done)
        submit call — pollingUrl itself is untouched."""
        monkeypatch.setattr(ev, "is_safe_host", _async_true)
        client = _FakeAsyncClient(
            [
                _FakeResponse(200, json_body={"requestId": "job-1"}),
                _FakeResponse(200, json_body={"choices": [{"message": {"content": "done"}}]}),
            ]
        )
        _patch_client(monkeypatch, client)

        result = await validate_endpoint(
            endpoint="http://model.example.com:8080",
            task_type="llm",
            is_sync_api=False,
            polling_url="http://model.example.com:8080/poll",
            poll_interval_ms=10,
        )

        assert result.is_valid is True
        assert client.post_calls[0] == "http://model.example.com:8080/v1/chat/completions"
        assert client.post_calls[1] == "http://model.example.com:8080/poll"


async def _async_true(_hostname):
    return True


async def _async_false(_hostname):
    return False
