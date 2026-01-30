"""
Request/response logging middleware for tracking NER API usage.

Uses structured JSON logging with trace correlation.
"""

import time
import os
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_logging import get_logger, get_correlation_id, get_organization

# Import OpenTelemetry to extract trace_id
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

# Get Jaeger URL from environment or use default
JAEGER_UI_URL = os.getenv("JAEGER_UI_URL", "http://localhost:16686")

# Get logger - but configure it to use root logger's handler for consistency
# This ensures logs go through the handler configured by configure_logging() in main.py
logger = get_logger(__name__, use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true")
# Remove the logger's own handlers and let it propagate to root logger
# This ensures all logs use the same handler configuration
logger.handlers.clear()
logger.propagate = True  # Allow propagation to root logger for consistent handling


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
        try:
            response = await call_next(request)
        except Exception:
            # If an exception occurs, FastAPI's exception handlers will catch it
            # and return a response. That response will come back through this middleware
            # So we re-raise to let the exception handler work
            raise

        # Calculate processing time
        processing_time = time.time() - start_time

        # Determine log level based on status code
        status_code = response.status_code
        
        # Extract trace_id from OpenTelemetry context for Jaeger URL
        # IMPORTANT: Extract AFTER request processing to ensure span is fully initialized
        trace_id = None
        jaeger_trace_url = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    span_context = current_span.get_span_context()
                    # Format trace_id as hex string (Jaeger format) - 32 hex characters
                    # Ensure trace_id is non-zero (valid trace) and span is valid
                    if span_context.is_valid and span_context.trace_id != 0:
                        trace_id = format(span_context.trace_id, '032x')
                        # Create full Jaeger URL - use /jaeger prefix for Jaeger UI
                        jaeger_trace_url = f"{JAEGER_UI_URL}/jaeger/trace/{trace_id}"
            except Exception as e:
                # If trace extraction fails, continue without it
                logger.debug(f"Failed to extract trace ID: {e}")
                pass
        
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
        # Add trace_id and Jaeger URL if available
        if trace_id:
            log_context["trace_id"] = trace_id
        if jaeger_trace_url:
            log_context["jaeger_trace_url"] = jaeger_trace_url

        # Log with appropriate level using structured logging
        # Skip logging 400-series errors - these are logged at gateway level only
        # Log 200-series (success) and 500-series (server errors) at service level
        if 200 <= status_code < 300:
            logger.info(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        elif 400 <= status_code < 500:
            # Don't log 400-series errors - gateway handles this to avoid duplicates
            pass
        else:
            logger.error(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context}
            )

        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"

        return response



