"""
AI4ICore Telemetry Library - Simplified for Phase 1

Provides distributed tracing with OpenTelemetry.
Phase 1: Console output for local development
Phase 2: Kafka → OpenSearch → Trace UI
"""

from .tracing import setup_tracing, get_tracer
from .standard_spans import StandardSpanManager, Status, StatusCode
from .config import TelemetryConfig

# ❌ REMOVED (Phase 1 - Jaeger/telemetry-service paused):
# from .plugin import TelemetryPlugin, create_telemetry_plugin, register_telemetry_plugin
# from .jaeger_client import JaegerQueryClient
# from .rbac_helper import get_organization_filter, extract_user_info

# ⏸️ KEPT for Phase 2 (not exported yet):
# from .opensearch_client import OpenSearchQueryClient
# from .ip_capture import extract_client_ip, add_ip_to_current_span
# from .ip_middleware import IPCaptureMiddleware

__all__ = [
    # Core tracing (Phase 1)
    "setup_tracing",
    "get_tracer",
    "TelemetryConfig",
    # Standard spans (used by 10+ services)
    "StandardSpanManager",
    "Status",
    "StatusCode",
    # Legacy/removed (kept in comments for documentation):
    # "TelemetryPlugin", "create_telemetry_plugin", "register_telemetry_plugin",  # Phase 1: not used
    # "JaegerQueryClient", "get_organization_filter", "extract_user_info",  # Phase 1: telemetry-service paused
    # Phase 2 additions (when Kafka exporter is added):
    # "extract_client_ip", "add_ip_to_current_span", "IPCaptureMiddleware",
]

__version__ = "1.0.0"
