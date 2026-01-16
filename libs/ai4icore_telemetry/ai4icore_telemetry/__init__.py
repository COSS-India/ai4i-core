"""
AI4ICore Telemetry Library

Provides distributed tracing and telemetry capabilities for AI4ICore services.
"""

from .tracing import setup_tracing, get_tracer

__all__ = [
    "setup_tracing",
    "get_tracer",
]

__version__ = "1.0.0"
