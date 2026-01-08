"""
Request/response logging middleware for tracking NMT API usage.

Uses structured JSON logging with trace correlation.
"""

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_logging import get_logger, get_correlation_id, get_organization

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
        
        # Process request first (this will trigger ObservabilityMiddleware which sets organization)
        # Note: FastAPI exception handlers (like RequestValidationError) will catch
        # exceptions and return responses, which will still come back through this middleware
        # We don't catch exceptions here - let FastAPI's exception handlers handle them
        # The response from exception handlers will still come back through this middleware
        # IMPORTANT: In FastAPI/Starlette, when an exception is raised in a dependency,
        # the exception handler catches it and returns a response. That response comes
        # back through call_next, NOT as an exception. So we should NOT catch exceptions
        # here - call_next will return the response from exception handlers.
        # However, we keep the try-except to match OCR's pattern and handle edge cases.
        try:
            response = await call_next(request)
        except Exception as exc:
            # If an exception occurs that wasn't caught by FastAPI's exception handlers,
            # we log it and re-raise. This should rarely happen.
            processing_time = time.time() - start_time
            logger.error(
                f"Unhandled exception in {method} {path}: {type(exc).__name__}: {exc}",
                exc_info=True,
                extra={
                    "context": {
                        "method": method,
                        "path": path,
                        "status_code": 500,
                        "duration_ms": round(processing_time * 1000, 2),
                        "client_ip": client_ip,
                        "user_agent": user_agent,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                }
            )
            raise

        # Calculate processing time
        processing_time = time.time() - start_time

        # Determine log level based on status code
        # This will work for both successful responses and error responses
        # returned by exception handlers
        status_code = response.status_code
        
        # Get organization from request.state first (set by ObservabilityMiddleware)
        # This is more reliable than contextvars in async middleware
        organization = getattr(request.state, "organization", None)
        
        # Fallback: try to get from context if request.state doesn't have it
        if not organization:
            try:
                organization = get_organization()
            except Exception:
                pass
        
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
        if organization:
            log_context["organization"] = organization

        # Log with appropriate level using structured logging
        # This ensures ALL responses (success and error) are logged
        # Wrap in try-except to ensure we always return the response even if logging fails
        try:
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
        except Exception as log_error:
            # If logging fails, log a basic message to ensure we don't lose the request
            # This should never happen, but ensures robustness
            try:
                logger.error(
                    f"Failed to log request {method} {path} - {status_code}: {log_error}",
                    exc_info=True
                )
            except Exception:
                # Last resort: print to stderr if all logging fails
                import sys
                print(f"CRITICAL: Failed to log request {method} {path} - {status_code}", file=sys.stderr)

        # Add processing time header
        try:
            response.headers["X-Process-Time"] = f"{processing_time:.3f}"
        except Exception:
            # If we can't add header, continue anyway
            pass

        return response
