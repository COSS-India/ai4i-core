"""
AI4ICore Logging Library

Structured JSON logging with trace correlation for AI4ICore microservices.
"""

__version__ = "1.0.0"
__author__ = "AI4I Team"

from .logger import get_logger, configure_logging
from .context import set_trace_id, get_trace_id, clear_trace_id, TraceContext, generate_trace_id
from .formatters import JSONFormatter
from .handlers import KafkaHandler
from .middleware import (
    CorrelationMiddleware,
    get_correlation_id,
    get_trace_id_from_request,
)

__all__ = [
    "get_logger",
    "configure_logging",
    "set_trace_id",
    "get_trace_id",
    "clear_trace_id",
    "TraceContext",
    "generate_trace_id",
    "JSONFormatter",
    "KafkaHandler",
    "CorrelationMiddleware",
    "get_correlation_id",
    "get_trace_id_from_request",
]

