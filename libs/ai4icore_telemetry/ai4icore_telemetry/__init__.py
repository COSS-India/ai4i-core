"""
AI4ICore Telemetry Library

Provides distributed tracing and telemetry capabilities for AI4ICore services.
"""

from .tracing import setup_tracing, get_tracer
from .opensearch_client import get_opensearch_client, create_log_index

__all__ = [
    "setup_tracing",
    "get_tracer",
    "get_opensearch_client",
    "create_log_index",
]

__version__ = "1.0.0"
