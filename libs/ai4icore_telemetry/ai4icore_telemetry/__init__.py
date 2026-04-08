"""
AI4ICore Telemetry Library

Provides distributed tracing and telemetry capabilities for AI4ICore services.
"""

from .tracing import setup_tracing, get_tracer
from .opensearch_client import OpenSearchQueryClient
from .jaeger_client import JaegerQueryClient
from .rbac_helper import get_organization_filter, extract_user_info
from .ip_capture import extract_client_ip, add_ip_to_current_span
from .ip_middleware import IPCaptureMiddleware
from .config import TelemetryConfig
from .standard_spans import StandardSpanManager
from .plugin import (
    TelemetryPlugin,
    create_telemetry_plugin,
    register_telemetry_plugin,
)

__all__ = [
    # Plugin pattern (recommended)
    "TelemetryPlugin",
    "TelemetryConfig",
    "create_telemetry_plugin",
    "register_telemetry_plugin",
    # Legacy functions (backward compatibility)
    "setup_tracing",
    "get_tracer",
    # Client utilities
    "OpenSearchQueryClient",
    "JaegerQueryClient",
    # Helper functions
    "get_organization_filter",
    "extract_user_info",
    "extract_client_ip",
    "add_ip_to_current_span",
    # Middleware
    "IPCaptureMiddleware",
    # Standard spans
    "StandardSpanManager",
]

__version__ = "1.0.0"
