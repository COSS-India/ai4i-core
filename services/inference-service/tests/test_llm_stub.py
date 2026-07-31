"""Unit tests for the LLM chat proxy stub (load-test parity with Triton stubs)."""

import pytest

from config import settings
from response_test.responses.audio_transcription_responses import (
    MEDIUM_AUDIO_BYTES,
    SMALL_AUDIO_BYTES,
)
from response_test.stub_dispatcher import (
    get_audio_stub_response,
    get_llm_stub_response,
)


@pytest.fixture
def stub_mode(monkeypatch):
    """Turn stub mode on for the duration of a test."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", True)


def _prompt_of_length(n: int) -> dict:
    return {"model": "stub", "messages": [{"role": "user", "content": "x" * n}]}


def test_returns_none_when_mode_is_off(monkeypatch):
    """With the flag off the chat path must reach the real upstream."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)

    assert get_llm_stub_response(_prompt_of_length(10)) is None


def test_classifies_by_prompt_length(stub_mode):
    """Prompt length picks SMALL / MEDIUM / LARGE buckets (200 / 1000 thresholds)."""
    contents = {
        get_llm_stub_response(_prompt_of_length(n))["choices"][0]["message"]["content"]
        for n in (10, 500, 1500)
    }

    assert len(contents) == 3


def test_body_is_openai_shaped_with_usage(stub_mode):
    """The stub is an OpenAI chat-completion body with a consistent usage block."""
    body = get_llm_stub_response(_prompt_of_length(10))

    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    usage = body["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_body_carries_the_fields_the_chat_route_bills_on(stub_mode):
    """set_billed_state reads usage, set_metric_labels reads model.

    Without both present the route would bill zero and label the metric with an
    empty model, silently, so this is the contract that keeps the stub usable
    for a billing-inclusive load test.
    """
    body = get_llm_stub_response(_prompt_of_length(10))

    assert body["usage"]["prompt_tokens"] > 0
    assert body["usage"]["completion_tokens"] > 0
    assert body["model"]


def test_returns_deep_copy(stub_mode):
    """Callers mutating the result must not corrupt the shared stub constants."""
    first = get_llm_stub_response(_prompt_of_length(10))
    first["choices"][0]["message"]["content"] = "mutated"
    second = get_llm_stub_response(_prompt_of_length(10))

    assert second["choices"][0]["message"]["content"] != "mutated"


def test_handles_missing_or_nonstring_messages(stub_mode):
    """Empty / multimodal payloads classify as SMALL instead of raising."""
    assert get_llm_stub_response({}) is not None
    assert get_llm_stub_response(
        {"messages": [{"role": "user", "content": [{"type": "image"}]}]}
    ) is not None


@pytest.mark.asyncio
async def test_proxy_traced_short_circuits_before_mms_and_upstream(stub_mode, monkeypatch):
    """Neither MMS resolution nor the upstream forward may run in stub mode."""
    from services.llm_service import OpenAIProxyService

    service = OpenAIProxyService()

    async def _fail(*args, **kwargs):
        raise AssertionError("stub mode must not reach MMS or the upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _fail)
    monkeypatch.setattr(service, "forward", _fail)

    status, body = await service.proxy_traced(
        path="/v1/chat/completions", payload=_prompt_of_length(10)
    )

    assert status == 200
    assert body["object"] == "chat.completion"


@pytest.mark.asyncio
async def test_proxy_traced_falls_through_when_mode_is_off(monkeypatch):
    """With the flag off the real resolution path must still run."""
    from services.llm_service import OpenAIProxyService

    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)
    service = OpenAIProxyService()
    called = {}

    async def _resolve(service_id, path):
        called["resolved"] = service_id
        raise LookupError("not found")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)

    status, _ = await service.proxy_traced(
        path="/v1/chat/completions", payload=_prompt_of_length(10)
    )

    assert called["resolved"] == "stub"
    assert status == 404


# ── /audio/* multipart passthrough ────────────────────────────────────────────

def _upload(nbytes: int) -> dict:
    return {"file": ("clip.wav", b"\x00" * nbytes, "audio/wav")}


def test_audio_stub_returns_none_when_mode_is_off(monkeypatch):
    """With the flag off the audio routes must reach the real upstream."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)

    assert get_audio_stub_response(_upload(1000), {"response_format": "json"}) is None


@pytest.mark.parametrize(
    "response_format,expected_type",
    [
        ("json", dict),
        ("verbose_json", dict),
        ("text", str),
        ("srt", str),
        ("vtt", str),
    ],
)
def test_audio_stub_body_type_follows_response_format(
    response_format, expected_type, stub_mode
):
    """_proxy_audio_upload picks JSONResponse vs PlainTextResponse off the body
    type, so the wrong type here changes the response content type."""
    body = get_audio_stub_response(_upload(1000), {"response_format": response_format})

    assert isinstance(body, expected_type)


def test_audio_stub_defaults_to_json_for_unknown_format(stub_mode):
    """Matches the route default rather than returning an uninterpretable shape."""
    body = get_audio_stub_response(_upload(1000), {"response_format": "nonsense"})

    assert isinstance(body, dict)
    assert "text" in body


def test_audio_stub_defaults_to_json_when_format_absent(stub_mode):
    """response_format is optional on the route and defaults to json."""
    body = get_audio_stub_response(_upload(1000), {})

    assert isinstance(body, dict)
    assert "text" in body


def test_audio_stub_sizes_by_uploaded_file_bytes(stub_mode):
    """Audio is bucketed on upload byte length, not character count."""
    small = get_audio_stub_response(_upload(SMALL_AUDIO_BYTES - 1), {})
    medium = get_audio_stub_response(_upload(SMALL_AUDIO_BYTES), {})
    large = get_audio_stub_response(_upload(MEDIUM_AUDIO_BYTES), {})

    assert len(small["text"]) < len(medium["text"]) < len(large["text"])


def test_audio_verbose_json_carries_scaled_segments(stub_mode):
    """verbose_json must look like a real transcription, not an empty envelope."""
    body = get_audio_stub_response(
        _upload(MEDIUM_AUDIO_BYTES), {"response_format": "verbose_json"}
    )

    assert body["task"] == "transcribe"
    assert body["duration"] > 0
    assert body["segments"]
    assert body["segments"][-1]["end"] == pytest.approx(body["duration"])


def test_audio_stub_returns_deep_copy(stub_mode):
    """Callers mutating the result must not corrupt the shared constants."""
    first = get_audio_stub_response(_upload(1000), {})
    first["text"] = "mutated"
    second = get_audio_stub_response(_upload(1000), {})

    assert second["text"] != "mutated"


@pytest.mark.asyncio
async def test_proxy_multipart_short_circuits_before_mms_and_upstream(
    stub_mode, monkeypatch
):
    """The audio passthrough must not reach MMS or the LLM upstream in stub mode."""
    from services.llm_service import OpenAIProxyService

    service = OpenAIProxyService()

    async def _fail(*args, **kwargs):
        raise AssertionError("stub mode must not reach MMS or the upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _fail)

    status, body = await service.proxy_multipart(
        path="/audio/transcriptions",
        files=_upload(1000),
        data={"model": "llm-service-1", "response_format": "json"},
    )

    assert status == 200
    assert "text" in body


@pytest.mark.asyncio
async def test_proxy_multipart_falls_through_when_mode_is_off(monkeypatch):
    """With the flag off the real resolution path must still run."""
    from services.llm_service import OpenAIProxyService

    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)
    service = OpenAIProxyService()
    called = {}

    async def _resolve(service_id, path):
        called["resolved"] = service_id
        raise LookupError("not found")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)

    status, _ = await service.proxy_multipart(
        path="/audio/transcriptions",
        files=_upload(1000),
        data={"model": "llm-service-1"},
    )

    assert called["resolved"] == "llm-service-1"
    assert status == 404
