"""
Request/response logging middleware for tracking Language Diarization API usage.

Uses structured JSON logging with trace correlation (same pattern as NER service)
so Fluent Bit can ship logs to OpenSearch.
"""

import time
import os
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ai4icore_logging import get_logger, get_correlation_id, get_organization

# Get structured logger configured by ai4icore_logging.configure_logging() in main.py
logger = get_logger(
    __name__,
    use_kafka=os.getenv("USE_KAFKA_LOGGING", "false").lower() == "true",
)
# Let it propagate to root so the shared JSON formatter/handlers apply
logger.handlers.clear()
logger.propagate = True


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

        # Get correlation ID (set by CorrelationMiddleware / observability)
        correlation_id = get_correlation_id(request)

        # Process request (FastAPI/exception handlers will still return a Response)
        try:
            response: Response = await call_next(request)
        except Exception:
            # Let FastAPI's exception handlers deal with it; response will still flow back
            raise

        # Calculate processing time
        processing_time = time.time() - start_time
        status_code = response.status_code

        # Organization from observability (if available)
        organization = getattr(request.state, "organization", None)
        if not organization:
            try:
                organization = get_organization()
            except Exception:
                organization = None

        # Build structured context
        log_context = {
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "service": "language-diarization-service",
        }

        if user_id is not None:
            log_context["user_id"] = user_id
        if api_key_id is not None:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        if organization:
            log_context["organization"] = organization

        # For successful inference calls, add extra markers
        if path.endswith("/inference") and 200 <= status_code < 300:
            log_context["operation"] = "language_diarization.inference"
            log_context["success"] = True

        # Skip 4xx logs to avoid duplicates with gateway; log 2xx and 5xx
        if 200 <= status_code < 300:
            logger.info(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context},
            )
        elif 400 <= status_code < 500:
            # Gateway-level logs are enough; avoid duplicate 4xx entries
            pass
        else:
            # 5xx and others
            logger.error(
                f"{method} {path} - {status_code} - {processing_time:.3f}s",
                extra={"context": log_context},
            )

        # Add processing time header
        response.headers["X-Process-Time"] = f"{processing_time:.3f}"
        if correlation_id:
            response.headers["X-Correlation-ID"] = correlation_id

        return response

