"""
AI4ICore Observability — single-call setup for FastAPI services.

Wires the request middleware + Prometheus /metrics endpoint onto an app.
Health endpoints belong in ``ai4i_core.bootstrap.health``, not here.
"""
from typing import Optional

from fastapi import FastAPI, Response

from .config import PluginConfig
from .metrics import MetricsCollector
from .middleware import ObservabilityMiddleware


def setup_observability(
    app: FastAPI,
    config: Optional[PluginConfig] = None,
) -> MetricsCollector:
    """Wire request middleware + Prometheus /metrics endpoint onto ``app``.

    Returns the ``MetricsCollector`` so callers can record custom metrics
    post-setup (e.g. emitting tokenizer-accurate LLM token counts from
    inside a route handler).

    When ``config.enabled`` is False, returns a fresh collector but does
    NOT register middleware or endpoints — callers can still use it for
    manual tracking, but nothing is exposed via HTTP.
    """
    config = config or PluginConfig()
    collector = MetricsCollector()

    if not config.enabled:
        return collector

    app.add_middleware(
        ObservabilityMiddleware,
        metrics_collector=collector,
        config=config,
    )

    @app.get(config.metrics_path)
    async def _metrics_endpoint():
        return Response(
            content=collector.render(),
            media_type="text/plain",
        )

    if config.debug:
        print("✅ AI4ICore Observability wired (middleware + /metrics)")

    return collector
