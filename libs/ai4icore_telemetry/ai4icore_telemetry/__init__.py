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

__all__ = [
    "setup_tracing",
    "get_tracer",
    "OpenSearchQueryClient",
    "JaegerQueryClient",
    "get_organization_filter",
    "extract_user_info",
    "extract_client_ip",
    "add_ip_to_current_span",
    "IPCaptureMiddleware",
]

__version__ = "1.0.0"
