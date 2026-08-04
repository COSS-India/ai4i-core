"""Unit tests for app/utils/endpoint_validator.py (AI4IDS-1844).

Covers:
- validate_response_shape: structural matching of a live response against
  an admin-supplied sample schema.
- test_inference (sync probe): reachability + response-shape gating.
- test_inference_async (poll-until-done probe): submit/poll dispatch,
  success after N polls, and the bounded-wait timeout path.
- validate_endpoint orchestrator: end-to-end is_valid outcome for each case.
"""

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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, json=None, headers=None):
        return self._responses.pop(0)


class _RaisingAsyncClient:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, json=None, headers=None):
        raise self._exc


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
        detail, body = await ev.test_inference(
            endpoint="http://model.example.com/infer", task_type="asr"
        )
        assert detail.status == ValidationStatus.PASSED
        assert body == {"output": [{"source": "x"}]}

    @pytest.mark.asyncio
    async def test_5xx_fails_without_body(self, monkeypatch):
        _patch_client(monkeypatch, _FakeAsyncClient([_FakeResponse(503, text="down")]))
        detail, body = await ev.test_inference(
            endpoint="http://model.example.com/infer", task_type="asr"
        )
        assert detail.status == ValidationStatus.FAILED
        assert body is None

    @pytest.mark.asyncio
    async def test_connect_error_produces_clear_message(self, monkeypatch):
        import httpx

        _patch_client(monkeypatch, _RaisingAsyncClient(httpx.ConnectError("refused")))
        detail, body = await ev.test_inference(
            endpoint="http://unreachable.example.com/infer", task_type="asr"
        )
        assert detail.status == ValidationStatus.FAILED
        assert "Could not connect" in detail.message
        assert body is None

    @pytest.mark.asyncio
    async def test_timeout_produces_clear_message(self, monkeypatch):
        import httpx

        _patch_client(monkeypatch, _RaisingAsyncClient(httpx.TimeoutException("slow")))
        detail, body = await ev.test_inference(
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
        detail, body = await ev.test_inference_async(
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
        detail, body = await ev.test_inference_async(
            endpoint="http://model.example.com/submit",
            polling_url="http://model.example.com/poll",
            poll_interval_ms=10,
            task_type="asr",
        )
        assert detail.status == ValidationStatus.FAILED
        assert "submit" in detail.message
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
        detail, body = await ev.test_inference_async(
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

        detail, body = await ev.test_inference_async(
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


async def _async_true(_hostname):
    return True


async def _async_false(_hostname):
    return False
