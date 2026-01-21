"""
Request/response logging middleware for tracking API Gateway usage.

Uses structured JSON logging with trace correlation, compatible with OpenSearch dashboards.
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
        response: Response
        try:
            response = await call_next(request)
        except Exception:
            # If an exception occurs, FastAPI's exception handlers will catch it
            # and return a response. That response will come back through this middleware.
            raise

        # Calculate processing time
        processing_time = time.time() - start_time

        # Determine log level based on status code
        status_code = response.status_code

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

