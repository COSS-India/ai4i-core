"""
Normalized Correlation Middleware for NER Service

Reimplements CorrelationMiddleware with built-in normalization to ensure correlation IDs
are always in W3C-compatible format (32 hex characters) from the moment they're set.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_logging.context import set_trace_id, generate_trace_id


class NormalizedCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Correlation middleware that normalizes correlation IDs to hex format immediately.
    
    This ensures correlation IDs are always in W3C-compatible format (32 hex chars)
    from the moment they're set, preventing UUID format IDs from appearing anywhere.
    """
    
    def __init__(self, app, header_name: str = "X-Correlation-ID"):
        super().__init__(app)
        self.header_name = header_name
    
    def _normalize_id(self, trace_id: str) -> str:
        """Normalize UUID format to hex format (32 hex chars)."""
        if trace_id and "-" in trace_id:
            return trace_id.replace("-", "")
        return trace_id
    
    async def dispatch(self, request: Request, call_next):
        """
        Extract/generate correlation ID, normalize it, and set it everywhere.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain
            
        Returns:
            Response object
        """
        # Try to create a span for correlation middleware
        try:
            from opentelemetry import trace
            tracer = trace.get_tracer(__name__)
            span_context = tracer.start_as_current_span("middleware.correlation")
        except Exception:
            tracer = None
            span_context = None
        
        try:
            # Extract correlation ID from headers
            correlation_id = request.headers.get(self.header_name)
            
            # Generate if missing
            if not correlation_id:
                correlation_id = generate_trace_id()
            
            # NORMALIZE immediately - this is the key fix!
            normalized_id = self._normalize_id(correlation_id)
            
            # Add to span (use normalized ID)
            if span_context:
                span = trace.get_current_span()
                if span:
                    span.set_attribute("correlation.id", normalized_id)
                    span.set_attribute("correlation.header", self.header_name)
                    span.set_attribute("correlation.generated", correlation_id not in request.headers)
            
            # Store NORMALIZED ID in request.state for application use
            request.state.correlation_id = normalized_id
            request.state.trace_id = normalized_id  # Alias for compatibility
            
            # Set NORMALIZED ID in logging context (so it appears in all logs)
            set_trace_id(normalized_id)
            
            try:
                # Process request
                response = await call_next(request)
                
                # Add NORMALIZED correlation ID to response headers
                response.headers[self.header_name] = normalized_id
                
                return response
            finally:
                # Clear trace ID from context after request (optional, but good practice)
                pass
        finally:
            if span_context:
                try:
                    span_context.__exit__(None, None, None)
                except Exception:
                    pass
