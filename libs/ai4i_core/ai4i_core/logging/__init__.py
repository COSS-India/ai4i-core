"""
AI4ICore structured logging.

Usage in a service:

    from ai4i_core.logging import configure_logging, RequestMiddleware

    configure_logging(service_name="my-service")
    app.add_middleware(RequestMiddleware)

Then use standard Python logging anywhere:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("something happened")
"""

from .logger import get_logger, configure_logging
from .formatters import JSONFormatter
from .middleware import RequestMiddleware
from .config import LoggingConfig, get_default_config
from .context import (
    generate_trace_id,
    set_trace_id,
    get_trace_id,
    reset_trace_id,
    set_tenant_id,
    get_tenant_id,
    reset_tenant_id,
)

__all__ = [
    "get_logger",
    "configure_logging",
    "JSONFormatter",
    "RequestMiddleware",
    "LoggingConfig",
    "get_default_config",
    "generate_trace_id",
    "set_trace_id",
    "get_trace_id",
    "reset_trace_id",
    "set_tenant_id",
    "get_tenant_id",
    "reset_tenant_id",
]
