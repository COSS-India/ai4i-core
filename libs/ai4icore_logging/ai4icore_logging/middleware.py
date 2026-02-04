"""
Correlation Middleware

Extracts correlation/trace ID from HTTP headers and sets it in logging context
for automatic inclusion in all log entries.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from typing import Optional

from .context import set_trace_id, get_trace_id, generate_trace_id


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for correlation ID (trace ID) management.
    
    Extracts X-Correlation-ID from request headers, generates one if missing,
    and sets it in the logging context so it appears in all log entries.
    
    Also stores the correlation ID in request.state for use in the application.
    """
    
    def __init__(self, app, header_name: str = "X-Correlation-ID"):
        """
        Initialize correlation middleware.
        
        Args:
            app: FastAPI application instance
            header_name: HTTP header name to look for correlation ID
        """
        super().__init__(app)
        self.header_name = header_name
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and set correlation ID in logging context.
        
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
            
            # Add to span
            if span_context:
                span = trace.get_current_span()
                if span:
                    span.set_attribute("correlation.id", correlation_id)
                    span.set_attribute("correlation.header", self.header_name)
                    span.set_attribute("correlation.generated", correlation_id not in request.headers)
            
            # Store in request.state for application use
            request.state.correlation_id = correlation_id
            request.state.trace_id = correlation_id  # Alias for compatibility
            
            # Set in logging context (so it appears in all logs)
            set_trace_id(correlation_id)
            
            try:
                # Process request
                response = await call_next(request)
                
                # Add correlation ID to response headers
                response.headers[self.header_name] = correlation_id
                
                return response
            finally:
                # Clear trace ID from context after request (optional, but good practice)
                # Note: This is optional since each request gets a new thread context
                # But it's good to clean up
                pass
        finally:
            if span_context:
                try:
                    span_context.__exit__(None, None, None)
                except Exception:
                    pass


def get_correlation_id(request: Request) -> Optional[str]:
    """
    Helper function to get correlation ID from request.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Correlation ID if available, None otherwise
    """
    return getattr(request.state, 'correlation_id', None)


def get_trace_id_from_request(request: Request) -> Optional[str]:
    """
    Helper function to get trace ID from request (alias for correlation_id).
    
    Args:
        request: FastAPI request object
        
    Returns:
        Trace ID if available, None otherwise
    """
    return getattr(request.state, 'trace_id', None) or getattr(request.state, 'correlation_id', None)

