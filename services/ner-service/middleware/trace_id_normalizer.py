"""
Trace ID Normalizer Middleware for NER Service

Normalizes correlation/trace IDs to W3C-compatible format (32 hex characters)
to ensure compatibility with Jaeger/OpenTelemetry trace ID validation.

This middleware runs after CorrelationMiddleware to normalize any UUID-format
correlation IDs to hex format before they're used in OpenTelemetry spans.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class TraceIdNormalizerMiddleware(BaseHTTPMiddleware):
    """
    Middleware that normalizes correlation/trace IDs to W3C-compatible format.
    
    Converts UUID format (with hyphens) to 32-character hex string format
    to ensure compatibility with Jaeger trace ID validation.
    """
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """
        Normalize correlation ID from headers, request.state, and logging context.
        Also ensures response headers have normalized correlation ID.
        
        This middleware normalizes in BOTH request and response phases to catch
        correlation IDs set by CorrelationMiddleware or other middleware.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain
            
        Returns:
            Response object
        """
        def normalize_id(trace_id: str) -> str:
            """Normalize UUID format to hex format (32 hex chars)."""
            if trace_id and "-" in trace_id:
                return trace_id.replace("-", "")
            return trace_id
        
        # PHASE 1: Normalize incoming header value early (before request processing)
        header_correlation_id = request.headers.get("X-Correlation-ID")
        if header_correlation_id and "-" in header_correlation_id:
            normalized_header_id = normalize_id(header_correlation_id)
            # Store normalized version in request.state early
            if not hasattr(request.state, "correlation_id"):
                request.state.correlation_id = normalized_header_id
                request.state.trace_id = normalized_header_id
        
        # Normalize any existing correlation_id in request.state (from earlier middleware)
        correlation_id = getattr(request.state, "correlation_id", None)
        if correlation_id and "-" in correlation_id:
            normalized_id = normalize_id(correlation_id)
            request.state.correlation_id = normalized_id
            request.state.trace_id = normalized_id
        
        # Normalize in logging context early (so logs show normalized IDs)
        try:
            from ai4icore_logging.context import get_trace_id, set_trace_id
            current_trace_id = get_trace_id()
            if current_trace_id and "-" in current_trace_id:
                normalized_trace_id = normalize_id(current_trace_id)
                set_trace_id(normalized_trace_id)
        except Exception:
            pass
        
        # Process request (this allows CorrelationMiddleware to potentially set/overwrite correlation_id)
        response = await call_next(request)
        
        # PHASE 2: Normalize again AFTER request processing (catches what CorrelationMiddleware set)
        correlation_id = getattr(request.state, "correlation_id", None)
        if correlation_id and "-" in correlation_id:
            normalized_id = normalize_id(correlation_id)
            request.state.correlation_id = normalized_id
            request.state.trace_id = normalized_id
        
        # Normalize in logging context again (in case it was overwritten)
        try:
            from ai4icore_logging.context import get_trace_id, set_trace_id
            current_trace_id = get_trace_id()
            if current_trace_id and "-" in current_trace_id:
                normalized_trace_id = normalize_id(current_trace_id)
                set_trace_id(normalized_trace_id)
        except Exception:
            pass
        
        # CRITICAL: Normalize correlation ID in response headers (this is what users copy!)
        response_correlation_id = response.headers.get("X-Correlation-ID")
        if response_correlation_id and "-" in response_correlation_id:
            response.headers["X-Correlation-ID"] = normalize_id(response_correlation_id)
        
        return response
