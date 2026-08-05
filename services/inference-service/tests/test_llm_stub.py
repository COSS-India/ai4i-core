"""Unit tests for the LLM chat proxy stub (load-test parity with Triton stubs)."""

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from config import settings
from response_test.responses.audio_transcription_responses import (
    MEDIUM_AUDIO_BYTES,
    SMALL_AUDIO_BYTES,
)
from response_test.stub_dispatcher import (
    get_audio_stub_response,
    get_llm_stub_response,
    get_llm_stream_stub,
)


@pytest.fixture
def stub_mode(monkeypatch):
    """Turn stub mode on for the duration of a test."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", True)


# What a resolved, published LLM service looks like coming back from MMS.
_SERVICE_INFO = {
    "is_published": True,
    "endpoint": "http://vllm.invalid",
    "adapter_config": {"model_name": "gemma-3-27b"},
    "tier_ids": [],
}


@pytest.fixture(scope="module")
def span_exporter():
    """Capture finished spans.

    The tracer provider can only be set once per process, so this is
    module-scoped and cleared per test rather than rebuilt.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # already set by another module in the same run
        pass
    return exporter


@pytest.fixture(autouse=True)
def _clear_spans(request):
    """Start every test with an empty exporter when one is in play."""
    if "span_exporter" in request.fixturenames:
        request.getfixturevalue("span_exporter").clear()


def _prompt_of_length(n: int) -> dict:
    return {"model": "stub", "messages": [{"role": "user", "content": "x" * n}]}


async def _drain(stream) -> list:
    """Consume a streaming generator to completion and return what it yielded.

    proxy_traced_stream only finalises its spans and token counts once the
    stream is fully drained, so tests must consume it rather than discard it.
    """
    return [chunk async for chunk in stream]


def _events(lines: list) -> list[dict]:
    """Parse the JSON payload out of every `data:` line except [DONE]."""
    import json

    out = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        body = line[len("data:"):].strip()
        if not body or body == "[DONE]":
            continue
        out.append(json.loads(body))
    return out


def _ai_inference_tokens(exporter) -> tuple:
    """(input_tokens, output_tokens) off the ai-inference span the PPU bills on."""
    for span in exporter.get_finished_spans():
        if span.name == "ai-inference":
            attrs = dict(span.attributes or {})
            return attrs.get("input_tokens"), attrs.get("output_tokens")
    raise AssertionError("no ai-inference span was emitted")


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
async def test_proxy_traced_stubs_the_upstream_but_still_resolves(stub_mode, monkeypatch):
    """The stub replaces the upstream POST only, not the whole method.

    MMS resolution is expected to run: the stub sits at the innermost seam so
    the model and ai-inference spans above it are still opened. Short-circuiting
    higher up skips both spans and silently drops PPU billing.
    """
    from services.llm_service import OpenAIProxyService

    service = OpenAIProxyService()
    resolved = {}

    async def _resolve(service_id, path):
        resolved["service_id"] = service_id
        return "http://vllm.invalid/v1/chat/completions", _SERVICE_INFO

    async def _no_upstream(*args, **kwargs):
        raise AssertionError("stub mode must not reach the LLM upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)
    monkeypatch.setattr(httpx.AsyncClient, "post", _no_upstream)

    status, body = await service.proxy_traced(
        path="/v1/chat/completions", payload=_prompt_of_length(10)
    )

    assert resolved["service_id"] == "stub"
    assert status == 200
    assert body["object"] == "chat.completion"


@pytest.mark.asyncio
async def test_stubbed_chat_emits_all_five_spans(stub_mode, monkeypatch, span_exporter):
    """Regression guard: the PPU Kafka consumer bills off the ai-inference span,
    and the LLM stub path must forward all 5 spans (request, guardrails, model,
    ai-inference, response-formatting).

    A stub that short-circuits above these spans still returns 200, so the only
    symptom is silently missing spans and zero billing. That is what this pins.
    """
    from services.llm_service import OpenAIProxyService
    from trace.request_span import traced_span

    service = OpenAIProxyService()

    async def _resolve(service_id, path):
        return "http://vllm.invalid/v1/chat/completions", _SERVICE_INFO

    async def _no_upstream(*args, **kwargs):
        raise AssertionError("stub mode must not reach the LLM upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)
    monkeypatch.setattr(httpx.AsyncClient, "post", _no_upstream)

    with traced_span("request", root=True, classify_status=True):
        await service.proxy_traced(
            path="/v1/chat/completions", payload=_prompt_of_length(10)
        )

    spans = {s.name: dict(s.attributes or {}) for s in span_exporter.get_finished_spans()}

    assert "request" in spans
    assert "guardrails" in spans
    assert "model" in spans
    assert "ai-inference" in spans
    assert "response-formatting" in spans
    # Billing reads these off the ai-inference span; zero here means no revenue.
    assert spans["ai-inference"]["input_tokens"] > 0
    assert spans["ai-inference"]["output_tokens"] > 0
    assert spans["ai-inference"]["service_id"] == "stub"
    # The model label must be the upstream model, not the fixture's literal.
    assert spans["model"]["model_name"] == "gemma-3-27b"
    # Hardcoded placeholder spans still carry request-identifying fields.
    assert spans["guardrails"]["service_id"] == "stub"
    assert spans["guardrails"]["result"] == "passed"
    # response-formatting is finalized after the model span updates model_name
    # from the (stubbed) upstream response, so it must reflect that, not the
    # pre-inference resolved value.
    assert spans["response-formatting"]["service_id"] == "stub"
    assert spans["response-formatting"]["model_name"] == "gemma-3-27b"


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


# ── streaming chat (SSE) ──────────────────────────────────────────────────────

def test_stream_stub_returns_none_when_mode_is_off(monkeypatch):
    """With the flag off the streaming path must reach the real upstream."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)

    assert get_llm_stream_stub(_prompt_of_length(10)) is None


@pytest.mark.asyncio
async def test_stream_stub_frames_sse_and_terminates_with_done(stub_mode):
    """Lines must be framed the way proxy_stream frames real upstream lines.

    One string per line with a trailing newline, blank separators between
    events, and the stream's own [DONE] terminator — clients key off that
    terminator rather than the connection closing.
    """
    lines = await _drain(get_llm_stream_stub(_prompt_of_length(10)))

    assert all(line.endswith("\n") for line in lines)
    assert lines[-2] == "data: [DONE]\n"
    assert lines[-1] == "\n"
    assert all(line == "\n" for line in lines[1::2])


@pytest.mark.asyncio
async def test_stream_stub_opens_with_role_and_closes_with_finish_reason(stub_mode):
    """OpenAI streaming order: role delta first, finish_reason before usage."""
    events = _events(await _drain(get_llm_stream_stub(_prompt_of_length(10))))

    assert events[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert events[-2]["choices"][0]["finish_reason"] == "stop"
    assert all(e["object"] == "chat.completion.chunk" for e in events)


@pytest.mark.asyncio
async def test_stream_stub_final_chunk_carries_usage(stub_mode):
    """The usage chunk is what _record_stream_usage bills off.

    Without it the ai-inference span keeps the zeros traced_inference seeds and
    the PPU consumer skips the message, so the request returns 200 and bills
    nothing at all.
    """
    events = _events(await _drain(get_llm_stream_stub(_prompt_of_length(10))))
    usage = events[-1]["usage"]

    assert events[-1]["choices"] == []
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    # Only the last chunk carries usage; an earlier one would be billed instead.
    assert all("usage" not in e for e in events[:-1])


@pytest.mark.asyncio
async def test_stream_stub_deltas_reassemble_the_buffered_content(stub_mode):
    """A client accumulating the deltas gets the buffered stub's reply verbatim."""
    payload = _prompt_of_length(500)
    events = _events(await _drain(get_llm_stream_stub(payload)))

    streamed = "".join(
        e["choices"][0]["delta"].get("content", "")
        for e in events
        if e["choices"]
    )

    assert streamed == get_llm_stub_response(payload)["choices"][0]["message"]["content"]


@pytest.mark.asyncio
async def test_stream_stub_sizes_by_prompt_length(stub_mode):
    """Prompt length picks the same SMALL / MEDIUM / LARGE buckets as buffered."""
    usages = []
    for n in (10, 500, 1500):
        events = _events(await _drain(get_llm_stream_stub(_prompt_of_length(n))))
        usages.append(events[-1]["usage"]["completion_tokens"])

    assert len(set(usages)) == 3
    assert usages == sorted(usages)


@pytest.mark.asyncio
async def test_stream_stub_chunk_count_scales_with_reply_length(stub_mode):
    """One delta per word, so per-chunk overhead is exercised realistically.

    A stub that returned the whole reply in one chunk would hide the per-chunk
    _record_stream_usage parse that real streaming pays on every token.
    """
    small = _events(await _drain(get_llm_stream_stub(_prompt_of_length(10))))
    large = _events(await _drain(get_llm_stream_stub(_prompt_of_length(1500))))

    assert len(large) > len(small) * 10


@pytest.mark.asyncio
async def test_stream_stub_does_not_sleep_when_delay_is_zero(stub_mode, monkeypatch):
    """Zero delay must skip the await entirely, not await sleep(0).

    sleep(0) still yields to the event loop once per chunk, which would cap
    throughput on the default configuration for no benefit.
    """
    import asyncio

    calls = []
    monkeypatch.setattr(settings, "LLM_STUB_STREAM_DELAY_MS", 0)

    async def _spy(seconds):
        calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _spy)
    await _drain(get_llm_stream_stub(_prompt_of_length(10)))

    assert calls == []


@pytest.mark.asyncio
async def test_stream_stub_paces_events_when_delay_is_set(stub_mode, monkeypatch):
    """A configured delay applies once per event, not once per line."""
    import asyncio

    calls = []
    monkeypatch.setattr(settings, "LLM_STUB_STREAM_DELAY_MS", 25)

    async def _spy(seconds):
        calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _spy)
    lines = await _drain(get_llm_stream_stub(_prompt_of_length(10)))

    data_lines = [line for line in lines if line.startswith("data:")]
    assert calls == [0.025] * len(data_lines)


@pytest.mark.asyncio
async def test_proxy_traced_stream_stubs_the_upstream_but_still_resolves(stub_mode, monkeypatch):
    """The stub replaces the upstream connection only, not the whole method.

    MMS resolution, the tier gate and the include_usage injection are all
    expected to run, matching what the buffered seam does in forward().
    """
    from services.llm_service import OpenAIProxyService

    service = OpenAIProxyService()
    resolved = {}

    async def _resolve(service_id, path):
        resolved["service_id"] = service_id
        return "http://vllm.invalid/v1/chat/completions", _SERVICE_INFO

    async def _no_upstream(*args, **kwargs):
        raise AssertionError("stub mode must not reach the LLM upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)
    monkeypatch.setattr(httpx.AsyncClient, "send", _no_upstream)

    kind, status, result = await service.proxy_traced_stream(
        path="/v1/chat/completions",
        payload={**_prompt_of_length(10), "stream": True},
    )
    lines = await _drain(result)

    assert resolved["service_id"] == "stub"
    assert (kind, status) == ("stream", 200)
    assert lines[-2] == "data: [DONE]\n"


@pytest.mark.asyncio
async def test_stubbed_stream_emits_all_five_spans(
    stub_mode, monkeypatch, span_exporter
):
    """Regression guard: the PPU Kafka consumer bills off the ai-inference span,
    and the LLM stub path must forward all 5 spans on the streaming path too.

    The streaming spans open lazily inside the returned generator, so a stub
    that short-circuited proxy_traced_stream instead of proxy_stream would still
    return 200 while emitting neither span and billing nothing.
    """
    from services.llm_service import OpenAIProxyService
    from trace.request_span import traced_span

    service = OpenAIProxyService()

    async def _resolve(service_id, path):
        return "http://vllm.invalid/v1/chat/completions", _SERVICE_INFO

    async def _no_upstream(*args, **kwargs):
        raise AssertionError("stub mode must not reach the LLM upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)
    monkeypatch.setattr(httpx.AsyncClient, "send", _no_upstream)

    with traced_span("request", root=True, classify_status=True):
        _, _, result = await service.proxy_traced_stream(
            path="/v1/chat/completions",
            payload={**_prompt_of_length(10), "stream": True},
        )
        await _drain(result)

    spans = {s.name: dict(s.attributes or {}) for s in span_exporter.get_finished_spans()}

    assert "request" in spans
    assert "guardrails" in spans
    assert "model" in spans
    assert "ai-inference" in spans
    assert "response-formatting" in spans
    # Billing reads these off the ai-inference span; zero here means no revenue.
    assert spans["ai-inference"]["input_tokens"] > 0
    assert spans["ai-inference"]["output_tokens"] > 0
    assert spans["ai-inference"]["service_id"] == "stub"
    # Resolved from adapter_config, never read back from the stream body.
    assert spans["model"]["model_name"] == "gemma-3-27b"
    # Hardcoded placeholder spans still carry request-identifying fields.
    assert spans["guardrails"]["service_id"] == "stub"
    assert spans["response-formatting"]["service_id"] == "stub"
    assert spans["response-formatting"]["model_name"] == "gemma-3-27b"


@pytest.mark.asyncio
async def test_stubbed_stream_bills_the_same_tokens_as_buffered(
    stub_mode, monkeypatch, span_exporter
):
    """Streaming and buffered must bill identically for the same prompt.

    Both are views of one fixture, so any divergence means a load test would
    report different revenue depending on whether the client set stream: true.
    """
    from services.llm_service import OpenAIProxyService
    from trace.request_span import traced_span

    service = OpenAIProxyService()

    async def _resolve(service_id, path):
        return "http://vllm.invalid/v1/chat/completions", _SERVICE_INFO

    async def _no_upstream(*args, **kwargs):
        raise AssertionError("stub mode must not reach the LLM upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)
    monkeypatch.setattr(httpx.AsyncClient, "post", _no_upstream)
    monkeypatch.setattr(httpx.AsyncClient, "send", _no_upstream)

    payload = _prompt_of_length(500)

    with traced_span("request", root=True, classify_status=True):
        await service.proxy_traced(path="/v1/chat/completions", payload=dict(payload))
    buffered = _ai_inference_tokens(span_exporter)

    span_exporter.clear()

    with traced_span("request", root=True, classify_status=True):
        _, _, result = await service.proxy_traced_stream(
            path="/v1/chat/completions", payload={**payload, "stream": True},
        )
        await _drain(result)
    streamed = _ai_inference_tokens(span_exporter)

    assert streamed == buffered
    assert all(count > 0 for count in streamed)


@pytest.mark.asyncio
async def test_stubbed_stream_publishes_usage_to_the_metering_context_vars(
    stub_mode, monkeypatch
):
    """ObservabilityMiddleware bills a stream off these, via the route's bridge.

    _bridge_llm_usage_to_request copies them onto request.state after the body
    drains, so a stream that left them unset would emit zero token metrics.
    """
    from ai4i_core.context import (
        get_llm_usage_input_tokens,
        get_llm_usage_model_name,
        get_llm_usage_output_tokens,
        set_llm_usage_input_tokens,
        set_llm_usage_model_name,
        set_llm_usage_output_tokens,
    )
    from services.llm_service import OpenAIProxyService

    set_llm_usage_input_tokens(None)
    set_llm_usage_output_tokens(None)
    set_llm_usage_model_name(None)

    service = OpenAIProxyService()

    async def _resolve(service_id, path):
        return "http://vllm.invalid/v1/chat/completions", _SERVICE_INFO

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)

    _, _, result = await service.proxy_traced_stream(
        path="/v1/chat/completions",
        payload={**_prompt_of_length(10), "stream": True},
    )
    await _drain(result)

    assert get_llm_usage_input_tokens() > 0
    assert get_llm_usage_output_tokens() > 0
    assert get_llm_usage_model_name() == "gemma-3-27b"


@pytest.mark.asyncio
async def test_proxy_stream_falls_through_when_mode_is_off(monkeypatch):
    """With the flag off proxy_stream must still open a real connection."""
    from services.llm_service import OpenAIProxyService

    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)
    service = OpenAIProxyService()
    called = {}

    async def _open_stream(upstream_url, payload):
        called["url"] = upstream_url
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(service, "open_stream", _open_stream)

    kind, status, _ = await service.proxy_stream(
        path="http://vllm.invalid/v1/chat/completions", payload=_prompt_of_length(10)
    )

    assert called["url"] == "http://vllm.invalid/v1/chat/completions"
    assert (kind, status) == ("error", 502)


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
async def test_proxy_multipart_stubs_the_upstream_and_still_emits_all_five_spans(
    stub_mode, monkeypatch, span_exporter
):
    """Audio stubs the upstream POST only, so all 5 spans are still emitted
    (request, guardrails, model, ai-inference isn't part of the audio
    passthrough, but the LLM-only guardrails/response-formatting pair is)."""
    from services.llm_service import OpenAIProxyService
    from trace.request_span import traced_span

    service = OpenAIProxyService()

    async def _resolve(service_id, path):
        return "http://vllm.invalid" + path, _SERVICE_INFO

    async def _no_upstream(*args, **kwargs):
        raise AssertionError("stub mode must not reach the LLM upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)
    monkeypatch.setattr(httpx.AsyncClient, "post", _no_upstream)

    with traced_span("request", root=True, classify_status=True):
        status, body = await service.proxy_multipart(
            path="/audio/transcriptions",
            files=_upload(1000),
            data={"model": "llm-service-1", "response_format": "json"},
        )

    spans = {s.name: dict(s.attributes or {}) for s in span_exporter.get_finished_spans()}

    assert status == 200
    assert "text" in body
    assert "request" in spans
    assert "guardrails" in spans
    assert "response-formatting" in spans
    assert spans["model"]["service_id"] == "llm-service-1"
    assert spans["guardrails"]["service_id"] == "llm-service-1"
    assert spans["response-formatting"]["service_id"] == "llm-service-1"
    assert spans["response-formatting"]["model_name"] == "gemma-3-27b"


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
