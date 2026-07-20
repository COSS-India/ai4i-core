"""
Unit tests for the /chat and /chat/completions instrumentation toggles —
LLM_CHAT_TRACING_ENABLED (routes/inference.py) and
LLM_CHAT_OBSERVABILITY_ENABLED (app_factory.py's _ChatAwareObservabilityMiddleware,
a local subclass — ai4i_core itself is untouched). Both default to "off" so
the stubbed LLM chat path gives a clean orchestrator-overhead baseline.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from ai4i_core.observability.config import PluginConfig
from ai4i_core.observability.middleware import ObservabilityMiddleware


# ── LLM_CHAT_TRACING_ENABLED — routes/inference.py ───────────────────────────


@pytest.mark.asyncio
async def test_chat_skips_request_span_by_default():
    from config import settings
    import routes.inference as inference_routes

    assert settings.LLM_CHAT_TRACING_ENABLED is False

    with patch.object(
        inference_routes.OpenAIProxyService, "proxy",
        new=AsyncMock(return_value=(200, {"choices": []})),
    ), patch.object(inference_routes, "traced_span") as mock_span:
        scope = {"type": "http", "method": "POST", "path": "/chat", "headers": []}
        request = Request(scope)
        await inference_routes._run_llm_chat(request, {"messages": []}, path="/v1/chat")

    mock_span.assert_not_called()


@pytest.mark.asyncio
async def test_chat_wraps_request_span_when_enabled():
    from config import settings
    import routes.inference as inference_routes

    settings.LLM_CHAT_TRACING_ENABLED = True
    try:
        with patch.object(
            inference_routes.OpenAIProxyService, "proxy",
            new=AsyncMock(return_value=(200, {"choices": []})),
        ), patch.object(inference_routes, "traced_span") as mock_span:
            scope = {"type": "http", "method": "POST", "path": "/chat", "headers": []}
            request = Request(scope)
            await inference_routes._run_llm_chat(request, {"messages": []}, path="/v1/chat")

        mock_span.assert_called_once()
        assert mock_span.call_args.args[0] == "request"
        assert mock_span.call_args.kwargs.get("root") is True
    finally:
        settings.LLM_CHAT_TRACING_ENABLED = False


# ── LLM_CHAT_OBSERVABILITY_ENABLED — app_factory._ChatAwareObservabilityMiddleware ──


def _build_app():
    """Mirrors app_factory._setup_observability but importable without
    booting the full app (which needs DB/Redis env at import time)."""
    import app_factory

    app = FastAPI()
    config = PluginConfig(enabled=True)
    app.add_middleware(
        app_factory._ChatAwareObservabilityMiddleware,
        metrics_collector=None,
        config=config,
    )

    @app.post("/api/v1/chat")
    async def chat():
        return {"ok": True}

    @app.post("/api/v1/nmt/inference")
    async def nmt():
        return {"ok": True}

    return app


def test_chat_path_skips_observability_by_default():
    from config import settings

    assert settings.LLM_CHAT_OBSERVABILITY_ENABLED is False
    app = _build_app()
    with patch.object(ObservabilityMiddleware, "_record_metrics", new=AsyncMock()) as mock_record:
        with TestClient(app) as client:
            resp = client.post("/api/v1/chat")
    assert resp.status_code == 200
    mock_record.assert_not_called()


def test_non_chat_path_still_records_metrics():
    app = _build_app()
    with patch.object(ObservabilityMiddleware, "_record_metrics", new=AsyncMock()) as mock_record:
        with TestClient(app) as client:
            resp = client.post("/api/v1/nmt/inference")
    assert resp.status_code == 200
    mock_record.assert_called_once()


def test_chat_path_records_metrics_when_enabled():
    from config import settings

    settings.LLM_CHAT_OBSERVABILITY_ENABLED = True
    try:
        app = _build_app()
        with patch.object(ObservabilityMiddleware, "_record_metrics", new=AsyncMock()) as mock_record:
            with TestClient(app) as client:
                resp = client.post("/api/v1/chat")
        assert resp.status_code == 200
        mock_record.assert_called_once()
    finally:
        settings.LLM_CHAT_OBSERVABILITY_ENABLED = False
