#!/usr/bin/env python3
"""
Unit tests for the /audio/transcriptions and /audio/translations passthrough.

These exercise the route + proxy_multipart in isolation against a stubbed
upstream — no live vLLM/gemma server required. End-to-end testing must wait
until the upstream team ships the OpenAI-spec /v1/audio/* routes (see
DESIGN_audio_llm_endpoints.md §2 for the contract).

Coverage mirrors the matrix in DESIGN_audio_llm_endpoints.md §5:
  1. multipart bytes forwarded byte-for-byte
  2. non-file form fields forwarded as data
  3. upstream 200 JSON  → passed through as JSONResponse
  4. upstream 200 text  → passed through as PlainTextResponse
  5. upstream 400 (OpenAI envelope) → passed through unchanged
  6. > 25 MB body         → 413 file_too_large BEFORE upstream call
  7. missing `file` field → 400 with param=file
  8. transport error      → 502 with OpenAI error envelope
  9. misconfigured upstream → 503 with OpenAI error envelope
"""

import asyncio
import io
import logging
import sys
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Stub service_info returned by resolve_upstream_url in integration tests.
_STUB_SERVICE_INFO = {
    "is_published": True,
    "tier_ids": [],
    "adapter_config": {"model_name": "google/gemma-4-E4B-it"},
    "endpoint": "http://upstream-stub",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_client(stub_proxy_multipart) -> TestClient:
    """Mount just the inference router on a fresh FastAPI app, with
    OpenAIProxyService.proxy_multipart patched to ``stub_proxy_multipart``."""
    # Import inside the helper so the patch lands on the symbol the router
    # actually resolves (services.llm_service.OpenAIProxyService).
    from routes.inference import router
    from services import llm_service

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Patch the proxy_multipart method on the class so every instance the
    # route constructs sees the stub.
    patcher = patch.object(
        llm_service.OpenAIProxyService,
        "proxy_multipart",
        new=AsyncMock(side_effect=stub_proxy_multipart),
    )
    patcher.start()

    client = TestClient(app)
    # Stash the patcher on the client so the caller can stop it.
    client._patcher = patcher  # type: ignore[attr-defined]
    return client


def _wav_bytes(n: int = 1024) -> bytes:
    """Synthetic WAV-ish payload — bytes don't have to be valid audio, only
    the byte stream identity is being tested."""
    return b"RIFF" + (b"\x00" * (n - 4))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_forwards_file_bytes_unchanged() -> None:
    """The bytes the upstream sees must equal the bytes the client sent."""
    captured: Dict[str, Any] = {}

    async def stub(path, *, files, data=None, request=None):
        captured["path"] = path
        captured["files"] = files
        captured["data"] = data
        return 200, {"text": "hello world"}

    client = _build_client(stub)
    try:
        wav = _wav_bytes(2048)
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("clip.wav", wav, "audio/wav")},
            data={"model": "llm-service-1"},
        )
        assert resp.status_code == 200, resp.text
        assert captured["path"] == "/audio/transcriptions", (
            f"upstream path should be /audio/transcriptions (no /v1/ prefix per "
            f"the deployed vLLM server's URL design); got {captured['path']!r}"
        )
        # files entry is (filename, bytes, content_type) — bytes must match.
        _, fwd_bytes, fwd_ctype = captured["files"]["file"]
        assert fwd_bytes == wav, "file bytes were modified in transit"
        assert fwd_ctype == "audio/wav"
        logger.info("   [PASS] file bytes forwarded byte-for-byte")
    finally:
        client._patcher.stop()


async def test_forwards_non_file_form_fields() -> None:
    """model, language, prompt, response_format, temperature all reach upstream."""
    captured: Dict[str, Any] = {}

    async def stub(path, *, files, data=None, request=None):
        captured["data"] = data
        return 200, {"text": "ok"}

    client = _build_client(stub)
    try:
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
            data={
                "model": "llm-service-1",
                "language": "hi",
                "prompt": "medical context",
                "response_format": "json",
                "temperature": "0.0",
            },
        )
        assert resp.status_code == 200, resp.text
        # `model` carries the service ID; proxy_multipart resolves MMS by it and
        # replaces it with the real upstream model. language, prompt,
        # response_format, temperature must always reach upstream.
        for key in ("model", "language", "prompt", "response_format", "temperature"):
            assert key in captured["data"], f"{key} missing from forwarded data"
        assert captured["data"]["language"] == "hi"
        logger.info("   [PASS] non-file form fields forwarded as data")
    finally:
        client._patcher.stop()


async def test_upstream_200_json_returned_unchanged() -> None:
    async def stub(path, *, files, data=None, request=None):
        return 200, {"text": "transcribed text"}

    client = _build_client(stub)
    try:
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
            data={"model": "llm-service-1"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {"text": "transcribed text"}
        logger.info("   [PASS] upstream 200 JSON passed through unchanged")
    finally:
        client._patcher.stop()


async def test_upstream_200_text_returned_as_plain_text() -> None:
    """When response_format=text the upstream returns a bare string body."""
    async def stub(path, *, files, data=None, request=None):
        return 200, "transcribed text only"

    client = _build_client(stub)
    try:
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
            data={"model": "llm-service-1", "response_format": "text"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert resp.text == "transcribed text only"
        logger.info("   [PASS] upstream 200 text passed through as text/plain")
    finally:
        client._patcher.stop()


async def test_upstream_400_passes_through() -> None:
    """Upstream's OpenAI-shape 400 envelope reaches the client unmodified."""
    upstream_400 = {
        "error": {
            "message": "Invalid `response_format`.",
            "type": "invalid_request_error",
            "param": "response_format",
            "code": "unsupported_response_format",
        }
    }

    async def stub(path, *, files, data=None, request=None):
        return 400, upstream_400

    client = _build_client(stub)
    try:
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
            data={"model": "llm-service-1", "response_format": "verbose_json"},
        )
        assert resp.status_code == 400
        assert resp.json() == upstream_400
        logger.info("   [PASS] upstream 400 envelope passed through verbatim")
    finally:
        client._patcher.stop()


async def test_file_too_large_returns_413() -> None:
    """A Content-Length over 25 MB short-circuits BEFORE the upstream call."""
    upstream_called = {"yes": False}

    async def stub(path, *, files, data=None, request=None):
        upstream_called["yes"] = True
        return 200, {"text": "should not reach here"}

    client = _build_client(stub)
    try:
        oversized = b"\x00" * (26 * 1024 * 1024)  # 26 MB
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("big.wav", oversized, "audio/wav")},
            data={"model": "llm-service-1"},
        )
        assert resp.status_code == 413, resp.text
        err = resp.json()["error"]
        assert err["code"] == "file_too_large"
        assert err["param"] == "file"
        assert upstream_called["yes"] is False, "upstream must not be called for 413"
        logger.info("   [PASS] >25 MB body returns 413 file_too_large; upstream not called")
    finally:
        client._patcher.stop()


async def test_missing_file_returns_422() -> None:
    """With typed File(...) params, FastAPI rejects missing required fields
    at the validation layer with its standard 422 envelope BEFORE our route
    runs. We accept this trade-off in exchange for proper Swagger docs."""
    async def stub(path, *, files, data=None, request=None):
        raise AssertionError("upstream must not be called when `file` is missing")

    client = _build_client(stub)
    try:
        # Pass form data WITHOUT a `file` part. We use the `files` arg with a
        # dummy non-`file` field to force multipart encoding.
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"_dummy": ("dummy.txt", b"x", "text/plain")},
            data={"model": "llm-service-1"},
        )
        assert resp.status_code == 422, resp.text
        # FastAPI shape: {"detail": [{"type": "missing", "loc": ["body", "file"], ...}]}
        detail = resp.json()["detail"]
        assert any(
            d.get("loc") == ["body", "file"] and d.get("type") == "missing"
            for d in detail
        ), f"expected a 'file' missing-field error in detail, got {detail!r}"
        logger.info("   [PASS] missing `file` field returns 422 with body.file=missing")
    finally:
        client._patcher.stop()


async def test_transport_error_returns_502_openai_shape() -> None:
    """When httpx raises RequestError, proxy_multipart maps it to 502."""
    # Patch the underlying httpx call so the real proxy_multipart runs and
    # exercises its 502 mapping. This also confirms the integration between
    # the route and the real proxy_multipart implementation.
    from routes.inference import router
    from services import llm_service

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    real_post = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
    with patch.object(httpx.AsyncClient, "post", real_post), \
         patch.object(
             llm_service.OpenAIProxyService,
             "resolve_upstream_url",
             new=AsyncMock(return_value=(
                 "http://upstream-stub/v1/audio/transcriptions",
                 _STUB_SERVICE_INFO,
             )),
         ):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
            data={"model": "llm-service-1"},
        )
        assert resp.status_code == 502, resp.text
        err = resp.json()["error"]
        assert err["type"] == "upstream_error"
        assert "unreachable" in err["message"]
        logger.info("   [PASS] transport error → 502 OpenAI envelope")


async def test_misconfigured_upstream_returns_503_openai_shape() -> None:
    """MMS returns no endpoint for service → 503 with OpenAI error envelope."""
    from routes.inference import router
    from services import llm_service

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Force resolve_upstream_url to raise the misconfig ValueError.
    with patch.object(
        llm_service.OpenAIProxyService,
        "resolve_upstream_url",
        new=AsyncMock(side_effect=ValueError("No endpoint configured in MMS.")),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/audio/transcriptions",
            files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
            data={"model": "llm-service-1"},
        )
        assert resp.status_code == 503, resp.text
        err = resp.json()["error"]
        assert err["type"] == "api_error"
        logger.info("   [PASS] misconfig → 503 OpenAI envelope")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all() -> bool:
    tests: List[Tuple[str, Any]] = [
        ("forwards file bytes byte-for-byte",        test_forwards_file_bytes_unchanged),
        ("forwards non-file form fields",            test_forwards_non_file_form_fields),
        ("upstream 200 JSON passed through",         test_upstream_200_json_returned_unchanged),
        ("upstream 200 text passed through as text", test_upstream_200_text_returned_as_plain_text),
        ("upstream 400 envelope passed through",     test_upstream_400_passes_through),
        ("file too large → 413",                     test_file_too_large_returns_413),
        ("missing file field → 422 (FastAPI)",       test_missing_file_returns_422),
        ("transport error → 502",                    test_transport_error_returns_502_openai_shape),
        ("misconfigured upstream → 503",             test_misconfigured_upstream_returns_503_openai_shape),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        logger.info(f"▶ {name}")
        try:
            await fn()
            passed += 1
        except Exception:
            failed += 1
            logger.exception(f"   [FAIL] {name}")

    logger.info("=" * 70)
    if failed == 0:
        logger.info(f"All {passed} tests passed")
    else:
        logger.info(f"{passed} passed, {failed} FAILED")
    logger.info("=" * 70)

    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_all())
    sys.exit(0 if ok else 1)
