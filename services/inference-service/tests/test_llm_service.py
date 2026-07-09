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
