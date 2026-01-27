"""
Request/response logging middleware for tracking API usage.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
import logging
import sys
import time

# Get logger and configure with JSONFormatter
logger = logging.getLogger(__name__)

# Only configure if not already configured
if not logger.handlers:
    # Import JSONFormatter from ai4icore_logging
    try:
        from ai4icore_logging import JSONFormatter
        import os
        
        # Add stdout handler with JSONFormatter
        handler = logging.StreamHandler(sys.stdout)
        service_name = os.getenv("SERVICE_NAME", "llm-service")
        formatter = JSONFormatter(service_name=service_name)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    except ImportError:
        # Fallback to basic logging if ai4icore_logging not available
        handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

# Disable propagation to prevent duplicate logs
logger.propagate = False


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware for tracking API usage."""
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """Log request and response information."""
        # Capture start time
        start_time = time.time()
        
        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Extract auth context from request.state if available
        user_id = getattr(request.state, 'user_id', None)
        api_key_id = getattr(request.state, 'api_key_id', None)
        
        # Process request
        response = await call_next(request)
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Determine log level based on status code
        status_code = response.status_code
        
        # Get correlation ID if available
        try:
            from ai4icore_logging import get_correlation_id
            correlation_id = get_correlation_id(request)
        except Exception:
            correlation_id = None
        
        # Build context for structured logging
        log_context = {
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        
        # Logging strategy to avoid duplicates:
        # - 200-299: Log here (successful requests - service level)
        # - 400-499: Do NOT log (handled by API Gateway)
        # - 500-599: Log here (service errors - service level)
        if 200 <= status_code < 300:
            # Success - log at INFO level
            logger.info(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        elif 500 <= status_code < 600:
            # Server error - log at ERROR level
            logger.error(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        # Do NOT log 400-499 errors - they are logged at API Gateway level
        
        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"
        
        return response
