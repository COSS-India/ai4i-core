"""Unit tests: the streaming LLM chat route bridges usage/labels onto
request.state on BOTH the success and error paths.

Regression: the "kind == error" branch in _run_llm_chat_stream returned a
JSONResponse without ever calling _bridge_llm_usage_to_request(), so a
failed streaming request carried no model_id — model_breakdown drops the
empty-model_id bucket entirely, so the failure silently vanished from the
model's totals instead of counting against its success_pct.
"""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, ".")

from ai4i_core.context import set_llm_usage_model_id

import routes.inference as inference_routes


def _fake_request() -> SimpleNamespace:
    return SimpleNamespace(
        url=SimpleNamespace(path="/v1/chat/completions"),
        method="POST",
        headers={},
        state=SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_error_branch_bridges_model_id_onto_request_state():
    # Simulates what _prepare_request() would have set before the failure
    # occurred (e.g. MMS resolved the service, then the upstream connection
    # itself failed) — proxy_traced_stream is mocked out entirely below, so
    # this stands in for that earlier step.
    set_llm_usage_model_id("hash-gemma-v1")
    fake_request = _fake_request()

    mock_service = MagicMock()
    mock_service.proxy_traced_stream = AsyncMock(
        return_value=("error", 502, {"detail": "Upstream LLM request failed"})
    )

    with patch.object(inference_routes, "OpenAIProxyService", return_value=mock_service):
        response = await inference_routes._run_llm_chat_stream(
            fake_request, {"model": "svc-1"}, path="/v1/chat/completions",
        )

    assert response.status_code == 502
    assert fake_request.state.model_id == "hash-gemma-v1"

    set_llm_usage_model_id(None)


@pytest.mark.asyncio
async def test_error_branch_defaults_model_id_to_empty_string_when_unresolved():
    """Resolution itself failed before any model_id was ever known — the
    bridge must still run (and land "" rather than leaving the attribute
    unset), not skip labeling entirely."""
    set_llm_usage_model_id(None)
    fake_request = _fake_request()

    mock_service = MagicMock()
    mock_service.proxy_traced_stream = AsyncMock(
        return_value=("error", 404, {"detail": "Service 'svc-1' not found"})
    )

    with patch.object(inference_routes, "OpenAIProxyService", return_value=mock_service):
        response = await inference_routes._run_llm_chat_stream(
            fake_request, {"model": "svc-1"}, path="/v1/chat/completions",
        )

    assert response.status_code == 404
    assert fake_request.state.model_id == ""
