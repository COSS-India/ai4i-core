"""
ai4icore_core — Consolidated core library for AI4I-Core microservices.

Replaces the previously separate packages:
  - ai4icore_exceptions       → ai4icore_core.exceptions
  - ai4icore_env              → ai4icore_core.env
  - ai4icore_constants        → ai4icore_core.constants
  - ai4icore_logging          → ai4icore_core.logging
  - ai4icore_auth             → ai4icore_core.auth
  - ai4icore_bootstrap        → ai4icore_core.bootstrap
  - ai4icore_observability    → ai4icore_core.observability
  - ai4icore_telemetry        → ai4icore_core.telemetry
  - ai4icore_model_management → ai4icore_core.platform_core (renamed)
  - ai4icore_service_base     → ai4icore_core.service_base

Subpackages are imported on demand. Use:

    from ai4icore_core.exceptions import AppError, register_exception_handlers
    from ai4icore_core.env import app_env
    from ai4icore_core.logging import get_logger, RequestLoggingMiddleware
    from ai4icore_core.auth import JWTVerifier, AuthMiddleware
    from ai4icore_core.bootstrap import init_database, get_db, BaseSchema
    from ai4icore_core.observability import ObservabilityPlugin, MetricsCollector
    from ai4icore_core.telemetry import setup_tracing, TelemetryPlugin
    from ai4icore_core.platform_core import ModelManagementPlugin, TritonClient
    from ai4icore_core.service_base import create_inference_app
"""

__version__ = "1.0.0"
__author__ = "AI4I Team"

__all__ = [
    "exceptions",
    "env",
    "constants",
    "logging",
    "auth",
    "bootstrap",
    "observability",
    "telemetry",
    "platform_core",
    "service_base",
]
