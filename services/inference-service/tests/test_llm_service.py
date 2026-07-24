"""Unit tests for OpenAIProxyService — URL resolution and proxy error mapping."""

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── resolve_upstream_url ──────────────────────────────────────────────────────

def test_resolve_uses_model_specific_endpoint(llm_service):
    llm_service.model_endpoints = {"gpt-4": "http://gpu-host:8000"}
    llm_service.default_endpoint = "http://default:8000"
    url = llm_service.resolve_upstream_url("gpt-4", "/v1/chat/completions")
    assert url == "http://gpu-host:8000/v1/chat/completions"


def test_resolve_falls_back_to_default_when_model_not_in_overrides(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://default:8000"
    url = llm_service.resolve_upstream_url("unknown-model", "/v1/chat/completions")
    assert url == "http://default:8000/v1/chat/completions"


def test_resolve_raises_when_no_endpoint_is_configured(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = ""
    with pytest.raises(ValueError, match="No upstream LLM endpoint configured"):
        llm_service.resolve_upstream_url("any-model", "/v1/chat/completions")


def test_resolve_strips_trailing_slash_from_base_url(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://default:8000/"
    url = llm_service.resolve_upstream_url(None, "/v1/chat/completions")
    assert url == "http://default:8000/v1/chat/completions"


def test_resolve_uses_default_when_model_is_none(llm_service):
    llm_service.model_endpoints = {"gpt-4": "http://other:9000"}
    llm_service.default_endpoint = "http://default:8000"
    url = llm_service.resolve_upstream_url(None, "/v1/chat")
    assert url == "http://default:8000/v1/chat"


# ── proxy — error mapping ─────────────────────────────────────────────────────

async def test_proxy_returns_503_when_no_endpoint_configured(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = ""
    status, body = await llm_service.proxy("/v1/chat/completions", {"model": "x"})
    assert status == 503
    assert "detail" in body


async def test_proxy_returns_502_on_connect_error(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"
    with patch.object(
        llm_service, "forward",
        side_effect=httpx.ConnectError("unreachable"),
    ):
        status, body = await llm_service.proxy("/v1/chat/completions", {"model": "x"})
    assert status == 502
    assert body["error"]["type"] == "upstream_error"


async def test_proxy_forwards_payload_and_returns_upstream_response(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"
    expected_body = {"choices": [{"message": {"content": "hi"}}]}
    with patch.object(
        llm_service, "forward",
        new_callable=AsyncMock,
        return_value=(200, expected_body),
    ):
        status, body = await llm_service.proxy(
            "/v1/chat/completions", {"model": "gemma", "messages": []}
        )
    assert status == 200
    assert body == expected_body


async def test_proxy_passes_through_upstream_4xx_unchanged(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"
    upstream_error = {"error": {"message": "bad request", "type": "invalid_request_error"}}
    with patch.object(
        llm_service, "forward",
        new_callable=AsyncMock,
        return_value=(400, upstream_error),
    ):
        status, body = await llm_service.proxy("/v1/chat/completions", {"model": "x"})
    assert status == 400
    assert body == upstream_error


# ── proxy_multipart — error mapping ──────────────────────────────────────────

async def test_proxy_multipart_returns_503_when_no_endpoint(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = ""
    status, body = await llm_service.proxy_multipart(
        "/audio/transcriptions",
        files={"file": ("clip.wav", b"RIFF", "audio/wav")},
        data={"model": "x"},
    )
    assert status == 503
    assert body["error"]["type"] == "api_error"


async def test_proxy_multipart_returns_502_on_connect_error(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"
    with patch("services.llm_service.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.ConnectError("unreachable")
        )
        status, body = await llm_service.proxy_multipart(
            "/audio/transcriptions",
            files={"file": ("clip.wav", b"RIFF", "audio/wav")},
            data={"model": "x"},
        )
    assert status == 502
    assert body["error"]["type"] == "upstream_error"


# ── proxy_stream — SSE passthrough ───────────────────────────────────────────

async def test_proxy_stream_passes_through_sse_lines_unchanged(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"

    mock_response = MagicMock()
    mock_response.status_code = 200

    async def aiter_lines():
        for line in (
            'data: {"choices": [{"delta": {"content": "hi"}}]}',
            "",
            "data: [DONE]",
        ):
            yield line

    mock_response.aiter_lines = aiter_lines
    mock_response.aclose = AsyncMock()
    mock_client = MagicMock()
    mock_client.aclose = AsyncMock()

    with patch.object(
        llm_service, "open_stream",
        new_callable=AsyncMock,
        return_value=(mock_client, mock_response),
    ):
        kind, status, gen = await llm_service.proxy_stream(
            "/v1/chat/completions", {"model": "gemma"}
        )

    assert kind == "stream"
    assert status == 200
    lines = [line async for line in gen]
    assert lines == [
        'data: {"choices": [{"delta": {"content": "hi"}}]}\n',
        "\n",
        "data: [DONE]\n",
    ]
    mock_response.aclose.assert_awaited_once()
    mock_client.aclose.assert_awaited_once()


async def test_proxy_stream_returns_error_on_upstream_failure(llm_service):
    from services.llm_service import UpstreamStreamError

    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"
    with patch.object(
        llm_service, "open_stream",
        side_effect=UpstreamStreamError(500, {"error": "boom"}),
    ):
        kind, status, body = await llm_service.proxy_stream(
            "/v1/chat/completions", {"model": "gemma"}
        )
    assert kind == "error"
    assert status == 500
    assert body == {"error": "boom"}


# ── proxy_traced_stream — stream_options.include_usage injection ────────────

async def test_proxy_traced_stream_injects_include_usage_when_absent(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"

    async def fake_gen():
        yield "data: [DONE]\n"

    captured_payload = {}

    async def fake_proxy_stream(path, payload):
        captured_payload.update(payload)
        return "stream", 200, fake_gen()

    with patch.object(llm_service, "proxy_stream", side_effect=fake_proxy_stream):
        kind, status, gen = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", {"model": "gemma", "messages": []}
        )
        assert [line async for line in gen] == ["data: [DONE]\n"]

    assert captured_payload["stream_options"] == {"include_usage": True}


async def test_proxy_traced_stream_sets_include_usage_when_caller_omits_it(llm_service):
    """A caller-supplied stream_options without include_usage must still get
    it injected — setdefault() on the whole dict would silently skip this
    and the request would bill as 0 tokens."""
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"

    async def fake_gen():
        yield "data: [DONE]\n"

    captured_payload = {}

    async def fake_proxy_stream(path, payload):
        captured_payload.update(payload)
        return "stream", 200, fake_gen()

    payload = {"model": "gemma", "messages": [], "stream_options": {"foo": "bar"}}
    with patch.object(llm_service, "proxy_stream", side_effect=fake_proxy_stream):
        kind, status, gen = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", payload
        )
        assert [line async for line in gen] == ["data: [DONE]\n"]

    assert captured_payload["stream_options"] == {"foo": "bar", "include_usage": True}


async def test_proxy_traced_stream_preserves_caller_include_usage_false(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"

    async def fake_gen():
        yield "data: [DONE]\n"

    captured_payload = {}

    async def fake_proxy_stream(path, payload):
        captured_payload.update(payload)
        return "stream", 200, fake_gen()

    payload = {"model": "gemma", "messages": [], "stream_options": {"include_usage": False}}
    with patch.object(llm_service, "proxy_stream", side_effect=fake_proxy_stream):
        kind, status, gen = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", payload
        )
        assert [line async for line in gen] == ["data: [DONE]\n"]

    assert captured_payload["stream_options"] == {"include_usage": False}


# ── proxy_traced_stream — usage accounting for billing ───────────────────────

async def test_proxy_traced_stream_parses_non_zero_usage_from_final_chunk(llm_service):
    llm_service.model_endpoints = {}
    llm_service.default_endpoint = "http://upstream:8000"

    async def fake_gen():
        yield 'data: {"choices": [{"delta": {"content": "hi"}}]}\n'
        yield 'data: {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 34}}\n'
        yield "data: [DONE]\n"

    async def fake_proxy_stream(path, payload):
        return "stream", 200, fake_gen()

    captured_attrs = {}

    def fake_log_span_attributes(span_name, span, attributes):
        if span_name == "ai-inference":
            captured_attrs.update(attributes)

    from trace import request_span as rs_module

    with patch.object(llm_service, "proxy_stream", side_effect=fake_proxy_stream), \
         patch.object(rs_module, "log_span_attributes", side_effect=fake_log_span_attributes):
        kind, status, gen = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", {"model": "gemma", "messages": []}
        )
        lines = [line async for line in gen]

    assert lines[-1] == "data: [DONE]\n"
    assert captured_attrs["input_tokens"] == 12
    assert captured_attrs["output_tokens"] == 34
