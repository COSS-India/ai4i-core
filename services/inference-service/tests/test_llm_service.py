"""Unit tests for OpenAIProxyService — MMS resolution and proxy error mapping."""

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# Reusable stub service_info returned by the MMS resolver.
_STUB_SERVICE_INFO = {
    "is_published": True,
    "tier_ids": ["tier-1"],
    "adapter_config": {"model_name": "google/gemma-4-E4B-it"},
    "endpoint": "http://vllm:8000",
}


# ── resolve_upstream_url ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_returns_url_and_service_info(llm_service):
    with patch("services.llm_service._resolver") as mock_resolver:
        mock_resolver.resolve_service = AsyncMock(return_value=_STUB_SERVICE_INFO)
        url, info = await llm_service.resolve_upstream_url("svc-1", "/v1/chat/completions")
    assert url == "http://vllm:8000/v1/chat/completions"
    assert info == _STUB_SERVICE_INFO


@pytest.mark.asyncio
async def test_resolve_strips_trailing_slash_from_base_url(llm_service):
    service_info = {**_STUB_SERVICE_INFO, "endpoint": "http://vllm:8000/"}
    with patch("services.llm_service._resolver") as mock_resolver:
        mock_resolver.resolve_service = AsyncMock(return_value=service_info)
        url, _ = await llm_service.resolve_upstream_url("svc-1", "/v1/chat/completions")
    assert url == "http://vllm:8000/v1/chat/completions"


@pytest.mark.asyncio
async def test_resolve_raises_lookup_error_when_service_not_found(llm_service):
    with patch("services.llm_service._resolver") as mock_resolver:
        mock_resolver.resolve_service = AsyncMock(side_effect=LookupError("not found"))
        with pytest.raises(LookupError):
            await llm_service.resolve_upstream_url("missing-svc", "/v1/chat/completions")


@pytest.mark.asyncio
async def test_resolve_raises_lookup_error_when_service_not_published(llm_service):
    unpublished = {**_STUB_SERVICE_INFO, "is_published": False}
    with patch("services.llm_service._resolver") as mock_resolver:
        mock_resolver.resolve_service = AsyncMock(return_value=unpublished)
        with pytest.raises(LookupError, match="not published"):
            await llm_service.resolve_upstream_url("unpublished-svc", "/v1/chat/completions")


@pytest.mark.asyncio
async def test_resolve_raises_value_error_when_endpoint_missing(llm_service):
    no_endpoint = {**_STUB_SERVICE_INFO, "endpoint": ""}
    with patch("services.llm_service._resolver") as mock_resolver:
        mock_resolver.resolve_service = AsyncMock(return_value=no_endpoint)
        with pytest.raises(ValueError, match="No endpoint configured"):
            await llm_service.resolve_upstream_url("svc-1", "/v1/chat/completions")


# ── proxy_traced — MMS resolution + tier gate + billing spans ─────────────────

@pytest.mark.asyncio
async def test_proxy_traced_returns_404_when_service_not_found(llm_service):
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(side_effect=LookupError("not found"))):
        status, body = await llm_service.proxy_traced(
            "/v1/chat/completions", {"model": "missing-svc", "messages": []}
        )
    assert status == 404
    assert "not found" in body["detail"].lower()


@pytest.mark.asyncio
async def test_proxy_traced_returns_503_when_mms_unavailable(llm_service):
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(side_effect=ConnectionError("mms down"))):
        status, body = await llm_service.proxy_traced(
            "/v1/chat/completions", {"model": "svc-1", "messages": []}
        )
    assert status == 503


@pytest.mark.asyncio
async def test_proxy_traced_returns_403_when_tier_not_entitled(llm_service):
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "tier-2"  # not in allowed_tiers

    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))):
        status, body = await llm_service.proxy_traced(
            "/v1/chat/completions",
            {"model": "svc-1", "messages": []},
            request=mock_request,
        )
    assert status == 403
    assert "quota" in body["detail"].lower()


@pytest.mark.asyncio
async def test_proxy_traced_passes_tier_check_when_entitled(llm_service):
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "tier-1"  # in allowed_tiers

    expected = {"choices": [{"message": {"content": "hi"}}], "model": "gemma", "usage": {}}
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))), \
         patch.object(llm_service, "forward",
                      new=AsyncMock(return_value=(200, expected))):
        status, body = await llm_service.proxy_traced(
            "/v1/chat/completions",
            {"model": "svc-1", "messages": []},
            request=mock_request,
        )
    assert status == 200
    assert body == expected


@pytest.mark.asyncio
async def test_proxy_traced_injects_model_name_from_adapter_config(llm_service):
    """Payload forwarded to upstream must contain model from MMS adapter_config."""
    captured = {}

    async def capture_forward(url, payload):
        captured["payload"] = payload
        return 200, {"choices": [], "model": "google/gemma-4-E4B-it", "usage": {}}

    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))), \
         patch.object(llm_service, "forward", side_effect=capture_forward):
        await llm_service.proxy_traced(
            "/v1/chat/completions",
            {"model": "svc-1", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert captured["payload"].get("model") == "google/gemma-4-E4B-it"


@pytest.mark.asyncio
async def test_proxy_traced_replaces_client_model_with_upstream_model(llm_service):
    """The client's `model` is the service ID; it must be replaced by the real
    upstream model from adapter_config before forwarding to vLLM."""
    captured = {}

    async def capture_forward(url, payload):
        captured["payload"] = payload
        return 200, {"choices": [], "model": "gemma", "usage": {}}

    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))), \
         patch.object(llm_service, "forward", side_effect=capture_forward):
        await llm_service.proxy_traced(
            "/v1/chat/completions",
            {"model": "svc-1", "messages": []},
        )
    # "svc-1" was the service ID sent as `model`; upstream must get the real model.
    assert captured["payload"]["model"] == "google/gemma-4-E4B-it"


@pytest.mark.asyncio
async def test_proxy_traced_returns_502_on_connect_error(llm_service):
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))), \
         patch.object(llm_service, "forward",
                      side_effect=httpx.ConnectError("unreachable")):
        status, body = await llm_service.proxy_traced(
            "/v1/chat/completions", {"model": "svc-1", "messages": []}
        )
    assert status == 502
    assert body["detail"] == "Upstream LLM request failed"


# ── proxy_multipart — error mapping ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_proxy_multipart_returns_404_when_service_not_found(llm_service):
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(side_effect=LookupError("not found"))):
        status, body = await llm_service.proxy_multipart(
            "/audio/transcriptions",
            files={"file": ("clip.wav", b"RIFF", "audio/wav")},
            data={"model": "missing-svc"},
        )
    assert status == 404
    assert body["error"]["type"] == "not_found"


@pytest.mark.asyncio
async def test_proxy_multipart_returns_503_when_mms_unavailable(llm_service):
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(side_effect=ValueError("no endpoint"))):
        status, body = await llm_service.proxy_multipart(
            "/audio/transcriptions",
            files={"file": ("clip.wav", b"RIFF", "audio/wav")},
            data={"model": "svc-1"},
        )
    assert status == 503
    assert body["error"]["type"] == "api_error"


@pytest.mark.asyncio
async def test_proxy_multipart_returns_502_on_connect_error(llm_service):
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/audio/transcriptions", _STUB_SERVICE_INFO))), \
         patch("services.llm_service.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.ConnectError("unreachable")
        )
        status, body = await llm_service.proxy_multipart(
            "/audio/transcriptions",
            files={"file": ("clip.wav", b"RIFF", "audio/wav")},
            data={"model": "svc-1"},
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
