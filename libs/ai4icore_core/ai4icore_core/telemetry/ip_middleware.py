"""
IP capture middleware for OpenTelemetry spans.

Adds client IP address to OTel spans for distributed tracing.
Must be added AFTER FastAPIInstrumentor.instrument_app().
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

from .ip_capture import add_ip_to_current_span

logger = logging.getLogger(__name__)


class IPCaptureMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds client IP to OpenTelemetry spans.

    Usage:
        from ai4icore_core.telemetry import IPCaptureMiddleware
        app.add_middleware(IPCaptureMiddleware)

    ✅ SIMPLIFIED:
    - Removed verbose docstring explaining OTel integration details
    - dispatch() method is intentionally minimal (middleware pattern)
    - Error handling is in add_ip_to_current_span() (separation of concerns)
    """

    async def dispatch(self, request: Request, call_next):
        """Capture IP and continue request chain."""
        add_ip_to_current_span(request)
        return await call_next(request)
