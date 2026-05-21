"""Middleware for per-request trace ID generation."""

from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_core.context import generate_trace_id, set_trace_id


class TraceIDMiddleware(BaseHTTPMiddleware):
    """Generate unique trace ID for each HTTP request.
    
    Ensures every request has its own trace_id that propagates
    through all logs and spans for that request.
    """

    async def dispatch(self, request, call_next):
        """Generate trace_id for this request before processing."""
        trace_id = generate_trace_id()
        set_trace_id(trace_id)
        
        response = await call_next(request)
        return response
