"""Middleware for per-request trace ID and endpoint path propagation."""

from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_core.context import generate_trace_id, set_trace_id, set_endpoint_path


class TraceIDMiddleware(BaseHTTPMiddleware):
    """Generate unique trace ID and capture endpoint path for each HTTP request.

    Ensures every request has its own trace_id that propagates
    through all logs and spans for that request, and stores the endpoint path
    for use in telemetry attributes.
    """

    async def dispatch(self, request, call_next):
        """Generate trace_id and capture endpoint path for this request before processing."""
        trace_id = generate_trace_id()
        set_trace_id(trace_id)
        set_endpoint_path(request.url.path)

        response = await call_next(request)
        return response
