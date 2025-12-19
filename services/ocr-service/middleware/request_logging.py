"""
Request/response logging middleware for tracking OCR API usage.

Uses structured JSON logging with trace correlation.
"""

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_logging import get_logger, get_correlation_id

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware for tracking API usage."""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        """Log request and response information with structured logging."""
        # Capture start time
        start_time = time.time()

        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Get correlation ID (set by CorrelationMiddleware)
        correlation_id = get_correlation_id(request)

        # Process request
        response = await call_next(request)

        # Calculate processing time
        processing_time = time.time() - start_time

        # Determine log level based on status code
        status_code = response.status_code
        
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

        # Log with appropriate level using structured logging
        if 200 <= status_code < 300:
            logger.info(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        elif 400 <= status_code < 500:
            logger.warning(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        else:
            logger.error(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )

        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"

        return response


