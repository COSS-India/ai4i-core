"""
Request/response logging middleware for tracking API Gateway usage.

Uses structured JSON logging with trace correlation, compatible with OpenSearch dashboards.
"""

import time
import os

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_logging import get_logger, get_correlation_id, get_organization

# Get Jaeger URL from environment or use default
JAEGER_UI_URL = os.getenv("JAEGER_UI_URL", "http://localhost:16686")

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request logging middleware for tracking API usage."""

    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """Log request and response information with structured logging."""
        # Import tracing utilities (best-effort – middleware must not fail if tracing is unavailable)
        try:
            from opentelemetry import trace  # type: ignore
            tracer = trace.get_tracer("api-gateway-service")
        except Exception:  # pragma: no cover - tracing is optional
            trace = None  # type: ignore
            tracer = None

        # ---- PRE-SPAN: very small span just for middleware pre-processing ----
        if tracer:
            try:
                with tracer.start_as_current_span("middleware.request_logging.pre") as span:
                    span.set_attribute("middleware.type", "request_logging")
                    span.set_attribute("http.method", request.method)
                    span.set_attribute("http.route", request.url.path)
            except Exception:
                # Never break request flow if tracing fails
                pass

        # Capture start time for total request duration (including downstream services)
        start_time = time.time()

        # Extract request info that we also use later for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)

        # Get correlation ID (set by CorrelationMiddleware)
        correlation_id = get_correlation_id(request)

        # Process request (this includes auth, routing and downstream services)
        response: Response
        try:
            response = await call_next(request)
        except Exception:
            # Let FastAPI's exception handlers deal with this – we only observe
            raise

        # Calculate total processing time
        processing_time = time.time() - start_time

        # Determine log level based on status code
        status_code = response.status_code

        # ---- POST-SPAN: tiny span for logging & response enrichment ----
        if tracer:
            try:
                with tracer.start_as_current_span("middleware.request_logging.post") as span:
                    span.set_attribute("middleware.type", "request_logging")
                    span.set_attribute("http.method", method)
                    span.set_attribute("http.route", path)
                    span.set_attribute("http.status_code", status_code)
                    span.set_attribute("processing_time_ms", round(processing_time * 1000, 2))
            except Exception:
                pass

        # Get organization from request.state first (set by ObservabilityMiddleware)
        # This is more reliable than contextvars in async middleware
        organization = getattr(request.state, "organization", None)

        # Fallback: try to get from context if request.state doesn't have it
        if not organization:
            try:
                organization = get_organization()
            except Exception:
                organization = None

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
        
        # Extract trace_id from OpenTelemetry context for Jaeger URL
        # IMPORTANT: Extract AFTER request processing to ensure span is fully initialized
        trace_id = None
        jaeger_trace_url = None
        if trace:  # trace is already imported in this file
            try:
                current_span = trace.get_current_span()
                if current_span:
                    span_context = current_span.get_span_context()
                    # Format trace_id as hex string (Jaeger format) - 32 hex characters
                    # Ensure trace_id is non-zero (valid trace) and span is valid
                    if span_context.is_valid and span_context.trace_id != 0:
                        trace_id = format(span_context.trace_id, '032x')
                        # Store only trace_id - OpenSearch will use URL template to construct full URL
                        jaeger_trace_url = trace_id
            except Exception as e:
                # If trace extraction fails, continue without it
                logger.debug(f"Failed to extract trace ID: {e}")
                pass
        
        # Add trace_id and Jaeger URL if available
        if trace_id:
            log_context["trace_id"] = trace_id
        if jaeger_trace_url:
            log_context["jaeger_trace_url"] = jaeger_trace_url
        
        # Add gateway error context if available (for service unavailable scenarios)
        gateway_error_service = getattr(request.state, "gateway_error_service", None)
        if gateway_error_service:
            log_context["gateway_error_service"] = gateway_error_service
            log_context["gateway_error_type"] = getattr(request.state, "gateway_error_type", "unknown")

        # Log with appropriate level using structured logging
        # Skip logging successful requests (200-299) - these are logged at service level
        # Skip logging server errors (500+) from downstream services - these are logged at service level to avoid duplicates
        # Log gateway-generated server errors (500+) - these indicate gateway issues (service unavailable, etc.)
        # Log authentication (401) and authorization (403) errors at gateway level
        # Other client errors (400, 404, etc.) are also logged at gateway level
        if 200 <= status_code < 300:
            # Don't log successful requests - let downstream services handle this
            pass
        elif 400 <= status_code < 500:
            # Log client errors (401, 403, etc.) for authentication/authorization tracking at gateway
            logger.warning(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context},
            )
        else:
            # For server errors (500+), only log if it's gateway-generated (service unavailable, etc.)
            # If it came from a downstream service, skip logging to avoid duplicates
            downstream_response = getattr(request.state, "downstream_response", False)
            if gateway_error_service:
                # Gateway-generated error (service down, connection error, etc.) - log it
                logger.error(
                    f"{method} {path} - {status_code} - {processing_time:.3f}s",
                    extra={"context": log_context},
                )
            elif not downstream_response:
                # Gateway-generated error (not from downstream) - log it
                logger.error(
                    f"{method} {path} - {status_code} - {processing_time:.3f}s",
                    extra={"context": log_context},
                )
            # else: downstream service returned 500+ - already logged at service level, skip to avoid duplicates

        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"

        return response

