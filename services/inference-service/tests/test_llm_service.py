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
    "model_id": "hash-gemma-v1",
}


async def _sse_lines(lines):
    """Stand in for proxy_stream's generator: yields already-framed SSE lines."""
    for line in lines:
        yield f"{line}\n"


async def _drain(stream):
    """Consume a streaming generator to completion and return what it yielded.

    proxy_traced_stream() only finalises its spans and token counts once the
    stream is fully drained, so tests must consume it rather than discard it.
    """
    return [chunk async for chunk in stream]


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


# ── streaming — include_usage injection ──────────────────────────────────────

def test_with_include_usage_injects_when_absent(llm_service):
    out = llm_service._with_include_usage({"model": "svc-1", "stream": True})
    assert out["stream_options"] == {"include_usage": True}


def test_with_include_usage_honours_explicit_false(llm_service):
    """A client that deliberately opts out must not be overridden."""
    out = llm_service._with_include_usage(
        {"model": "svc-1", "stream_options": {"include_usage": False}}
    )
    assert out["stream_options"]["include_usage"] is False


def test_with_include_usage_preserves_other_stream_options(llm_service):
    out = llm_service._with_include_usage(
        {"model": "svc-1", "stream_options": {"something_else": 1}}
    )
    assert out["stream_options"] == {"something_else": 1, "include_usage": True}


def test_with_include_usage_replaces_non_dict_stream_options(llm_service):
    """A malformed stream_options must not crash the request."""
    out = llm_service._with_include_usage({"model": "svc-1", "stream_options": "bogus"})
    assert out["stream_options"] == {"include_usage": True}


def test_with_include_usage_does_not_mutate_caller_payload(llm_service):
    payload = {"model": "svc-1", "stream": True}
    llm_service._with_include_usage(payload)
    assert "stream_options" not in payload


# ── streaming — proxy_traced_stream shares the buffered path's pre-flight ─────

@pytest.mark.asyncio
async def test_proxy_traced_stream_returns_404_when_service_not_found(llm_service):
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(side_effect=LookupError("not found"))):
        kind, status, _ = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", {"model": "missing-svc", "stream": True}
        )
    assert kind == "error"
    assert status == 404


@pytest.mark.asyncio
async def test_proxy_traced_stream_returns_503_when_mms_unavailable(llm_service):
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(side_effect=ConnectionError("mms down"))):
        kind, status, _ = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", {"model": "svc-1", "stream": True}
        )
    assert kind == "error"
    assert status == 503


@pytest.mark.asyncio
async def test_proxy_traced_stream_enforces_tier_gate(llm_service):
    """Streaming must not be a way around the entitlement check."""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "tier-2"  # not in allowed_tiers

    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))):
        kind, status, body = await llm_service.proxy_traced_stream(
            "/v1/chat/completions",
            {"model": "svc-1", "stream": True},
            request=mock_request,
        )
    assert kind == "error"
    assert status == 403
    assert "quota" in body["detail"].lower()


@pytest.mark.asyncio
async def test_proxy_traced_stream_injects_upstream_model_and_include_usage(llm_service):
    """The streaming payload gets the same adapter_config model swap as JSON,
    plus stream_options so the usage chunk is emitted."""
    captured = {}

    async def capture_stream(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return "stream", 200, _sse_lines([])

    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))), \
         patch.object(llm_service, "proxy_stream", side_effect=capture_stream):
        kind, _, result = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", {"model": "svc-1", "stream": True}
        )
        await _drain(result)

    assert kind == "stream"
    assert captured["payload"]["model"] == "google/gemma-4-E4B-it"
    assert captured["payload"]["stream_options"]["include_usage"] is True
    # proxy_stream receives the resolved upstream URL, not the bare route path.
    assert captured["path"] == "http://vllm:8000/v1/chat/completions"


@pytest.mark.asyncio
async def test_proxy_traced_stream_passes_sse_lines_through_untouched(llm_service):
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        "",
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "",
        "data: [DONE]",
    ]
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))), \
         patch.object(llm_service, "proxy_stream",
                      new=AsyncMock(return_value=("stream", 200, _sse_lines(lines)))):
        _, _, result = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", {"model": "svc-1", "stream": True}
        )
        received = await _drain(result)

    assert received == [f"{line}\n" for line in lines]


@pytest.mark.asyncio
async def test_proxy_traced_stream_records_usage_from_final_chunk(llm_service):
    """Tokens from the usage chunk must reach the ai4i_core context vars, which
    is how ObservabilityMiddleware bills a stream without buffering it."""
    from ai4i_core.context import (
        get_llm_usage_input_tokens,
        get_llm_usage_model_id,
        get_llm_usage_model_name,
        get_llm_usage_output_tokens,
        set_llm_usage_input_tokens,
        set_llm_usage_model_id,
        set_llm_usage_model_name,
        set_llm_usage_output_tokens,
    )

    set_llm_usage_input_tokens(None)
    set_llm_usage_output_tokens(None)
    set_llm_usage_model_name(None)
    set_llm_usage_model_id(None)

    lines = [
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":19,"completion_tokens":82,"total_tokens":101}}',
        "data: [DONE]",
    ]
    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))), \
         patch.object(llm_service, "proxy_stream",
                      new=AsyncMock(return_value=("stream", 200, _sse_lines(lines)))):
        _, _, result = await llm_service.proxy_traced_stream(
            "/v1/chat/completions", {"model": "svc-1", "stream": True}
        )
        await _drain(result)

    assert get_llm_usage_input_tokens() == 19
    assert get_llm_usage_output_tokens() == 82
    # The model span carries the real upstream model, not the service ID.
    assert get_llm_usage_model_name() == "google/gemma-4-E4B-it"
    # Registry identity — set from MMS's service_info, not the response body.
    assert get_llm_usage_model_id() == "hash-gemma-v1"


@pytest.mark.asyncio
async def test_prepare_request_sets_model_id_from_service_info(llm_service):
    """model_id is known as soon as MMS resolves the service — unlike
    model_name, it doesn't depend on the upstream response, so both the
    buffered and streaming paths get it via the shared _prepare_request."""
    from ai4i_core.context import get_llm_usage_model_id, set_llm_usage_model_id

    set_llm_usage_model_id(None)

    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", _STUB_SERVICE_INFO))):
        await llm_service._prepare_request("/v1/chat/completions", {"model": "svc-1"})

    assert get_llm_usage_model_id() == "hash-gemma-v1"


@pytest.mark.asyncio
async def test_prepare_request_defaults_model_id_to_empty_string(llm_service):
    from ai4i_core.context import get_llm_usage_model_id, set_llm_usage_model_id

    set_llm_usage_model_id(None)
    service_info_without_model_id = {k: v for k, v in _STUB_SERVICE_INFO.items() if k != "model_id"}

    with patch.object(llm_service, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", service_info_without_model_id))):
        await llm_service._prepare_request("/v1/chat/completions", {"model": "svc-1"})

    assert get_llm_usage_model_id() == ""


def test_record_stream_usage_records_genuine_zero_usage(llm_service):
    """A real all-zero usage block must be recorded, not mistaken for absent."""
    infer_attrs = {}
    llm_service._record_stream_usage(
        'data: {"usage":{"prompt_tokens":0,"completion_tokens":0}}', infer_attrs
    )
    assert infer_attrs["input_tokens"] == 0
    assert infer_attrs["output_tokens"] == 0


@pytest.mark.parametrize("line", [
    "data: [DONE]",
    "",
    ": keep-alive comment",
    'data: {"choices":[{"delta":{"content":"hi"}}]}',
    "data: not-json",
])
def test_record_stream_usage_ignores_non_usage_lines(llm_service, line):
    infer_attrs = {}
    llm_service._record_stream_usage(line, infer_attrs)
    assert infer_attrs == {}


@pytest.mark.asyncio
async def test_open_stream_raises_upstream_stream_error_on_4xx(llm_service):
    """A 4xx before any SSE body must surface as a normal JSON error, so the
    route can answer with JSON instead of an empty event-stream."""
    from services.llm_service import UpstreamStreamError

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.aread = AsyncMock(return_value=b'{"detail":"bad request"}')
    mock_response.aclose = AsyncMock()

    with patch("services.llm_service.httpx.AsyncClient") as mock_client_cls:
        client = mock_client_cls.return_value
        client.build_request = MagicMock(return_value=MagicMock())
        client.send = AsyncMock(return_value=mock_response)
        client.aclose = AsyncMock()

        with pytest.raises(UpstreamStreamError) as exc_info:
            await llm_service.open_stream("http://vllm:8000/v1/chat/completions", {})

    assert exc_info.value.status_code == 400
    assert exc_info.value.body == {"detail": "bad request"}


@pytest.mark.asyncio
async def test_proxy_stream_maps_upstream_error_to_error_tuple(llm_service):
    from services.llm_service import UpstreamStreamError

    with patch.object(llm_service, "open_stream",
                      new=AsyncMock(side_effect=UpstreamStreamError(429, {"detail": "rate limited"}))):
        kind, status, body = await llm_service.proxy_stream(
            "http://vllm:8000/v1/chat/completions", {}
        )
    assert (kind, status) == ("error", 429)
    assert body == {"detail": "rate limited"}


@pytest.mark.asyncio
async def test_proxy_stream_maps_transport_error_to_502(llm_service):
    with patch.object(llm_service, "open_stream",
                      new=AsyncMock(side_effect=httpx.ConnectError("unreachable"))):
        kind, status, body = await llm_service.proxy_stream(
            "http://vllm:8000/v1/chat/completions", {}
        )
    assert (kind, status) == ("error", 502)
    assert body["error"]["type"] == "upstream_error"


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
