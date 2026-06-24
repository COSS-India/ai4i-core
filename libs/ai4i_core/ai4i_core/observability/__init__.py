"""
ai4i_core.observability — Request-level Prometheus metrics for FastAPI services.

Usage::

    from ai4i_core.observability import setup_observability, PluginConfig

    collector = setup_observability(app)
    # collector.track_* for manual metric emission from route handlers
"""

from .config import PluginConfig
from .metrics import MetricsCollector
from .middleware import ObservabilityMiddleware
from .plugin import setup_observability

__all__ = [
    "setup_observability",
    "MetricsCollector",
    "PluginConfig",
    "ObservabilityMiddleware",
]
