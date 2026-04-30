"""
IP Capture Middleware for FastAPI

Middleware that automatically captures client IP addresses from requests
and adds them to OpenTelemetry spans for distributed tracing.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

from .ip_capture import add_ip_to_current_span

logger = logging.getLogger(__name__)


class IPCaptureMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that captures client IP addresses and adds them to OpenTelemetry spans.
    
    This middleware should be added after FastAPIInstrumentor has been configured,
    so that HTTP request spans are already created when this middleware runs.
    
    Usage:
        from ai4icore_telemetry import IPCaptureMiddleware
        
        app.add_middleware(IPCaptureMiddleware)
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and add IP address to current span.
        
        Args:
            request: FastAPI Request object
            call_next: Next middleware/route handler in the chain
            
        Returns:
            Response from the next handler
        """
        # Add IP to the current OpenTelemetry span (if available)
        # This will silently fail if tracing is not set up or no span exists
        add_ip_to_current_span(request)
        
        # Continue with the request
        response = await call_next(request)
        return response
