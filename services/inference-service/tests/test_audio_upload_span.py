"""Unit test: an oversized /audio/* upload must still produce a "model" span.

Regression: _proxy_audio_upload()'s 25 MB cap (routes/inference.py) returned
413 before ever calling proxy_multipart() — the only code that creates any
span for this route family — so an oversized upload produced zero telemetry
at all: no span, no trace row, nothing in the logs dashboard. This is the
same root bug the rest of this ticket fixes (a rejection short-circuiting
before any span-creating code runs), one layer higher, in the route itself
rather than inside OpenAIProxyService.

Uses pytest-asyncio directly (unlike test_audio_passthrough.py, whose
undecorated async def tests don't run under pytest in this environment) so
this regression is actually verified in CI, not just on paper.
"""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, ".")

import routes.inference as inference_routes
import trace.request_span as request_span_module


def _fake_upload(size_bytes: int) -> SimpleNamespace:
    return SimpleNamespace(
        filename="big.wav",
        content_type="audio/wav",
        read=AsyncMock(return_value=b"\x00" * size_bytes),
    )


@pytest.fixture
def capture_finalize_span():
    """Same seam used in tests/test_llm_service.py: patch finalize_span to
    record every (attrs, kwargs) call, so tests can assert on the real
    span attrs a traced_span block finalizes with."""
    calls = []

    def _capture(span, attributes, **kwargs):
        calls.append((dict(attributes), kwargs))

    with patch.object(request_span_module, "finalize_span", side_effect=_capture):
        yield calls


@pytest.mark.asyncio
async def test_oversized_upload_emits_model_span_before_returning_413(
    capture_finalize_span,
):
    fake_request = SimpleNamespace(
        url=SimpleNamespace(path="/audio/transcriptions"),
        method="POST",
        headers={},
    )
    oversized_file = _fake_upload(26 * 1024 * 1024)  # > 25 MB

    with patch.object(
        inference_routes.OpenAIProxyService, "proxy_multipart",
        new=AsyncMock(side_effect=AssertionError(
            "proxy_multipart() must not be called for an oversized upload"
        )),
    ):
        response = await inference_routes._proxy_audio_upload(
            fake_request, oversized_file, {"model": "svc-1"}, "/audio/transcriptions",
        )

    assert response.status_code == 413

    assert len(capture_finalize_span) == 1, (
        f"expected exactly one span finalized, got {len(capture_finalize_span)}"
    )
    model_attrs, _ = capture_finalize_span[0]
    assert model_attrs["task_type"] == "LLM"
    assert model_attrs["service_id"] == "svc-1"
    assert model_attrs["status"] == "failure"
    assert model_attrs["status_code"] == 413


@pytest.mark.asyncio
async def test_undersized_upload_still_reaches_proxy_multipart(capture_finalize_span):
    """Sanity check: the fix must not accidentally short-circuit uploads
    that are within the cap."""
    fake_request = SimpleNamespace(
        url=SimpleNamespace(path="/audio/transcriptions"),
        method="POST",
        headers={},
    )
    small_file = _fake_upload(1024)  # 1 KB, well under the cap

    with patch.object(
        inference_routes.OpenAIProxyService, "proxy_multipart",
        new=AsyncMock(return_value=(200, {"text": "ok"})),
    ) as mock_proxy_multipart:
        response = await inference_routes._proxy_audio_upload(
            fake_request, small_file, {"model": "svc-1"}, "/audio/transcriptions",
        )

    assert response.status_code == 200
    mock_proxy_multipart.assert_awaited_once()
