"""
Global error handler middleware for consistent NER error responses.

Copied from OCR service to keep behavior and structure consistent.
"""

import logging
import time
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from middleware.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ErrorDetail,
    RateLimitExceededError,
)

# Import OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False

logger = logging.getLogger(__name__)


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ):  # type: ignore[unused-argument]
        """Handle authentication errors."""
        # Use message attribute if available, otherwise use detail or str(exc)
        message = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        error_detail = ErrorDetail(
            message=message,
            code="AUTHENTICATION_ERROR",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=401,
            content={"detail": error_detail.dict()},
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        request: Request, exc: AuthorizationError
    ):  # type: ignore[unused-argument]
        """Handle authorization errors."""
        # Use message attribute if available, otherwise use detail or str(exc)
        message = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        error_detail = ErrorDetail(
            message=message,
            code="AUTHORIZATION_ERROR",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=403,
            content={"detail": error_detail.dict()},
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_error_handler(
        request: Request, exc: RateLimitExceededError
    ):  # type: ignore[unused-argument]
        """Handle rate limit exceeded errors."""
        error_detail = ErrorDetail(
            message=exc.message,
            code="RATE_LIMIT_EXCEEDED",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=429,
            content={"detail": error_detail.dict()},
            headers={"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ):  # type: ignore[unused-argument]
        """Handle generic HTTP exceptions."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="HTTP_ERROR",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_detail.dict()},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ):  # type: ignore[unused-argument]
        """Handle unexpected exceptions."""
        # Capture full exception in trace span
        if TELEMETRY_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.code", "INTERNAL_ERROR")
                    current_span.set_attribute("error.message", str(exc))
                    current_span.set_attribute("error.type", type(exc).__name__)
                    current_span.set_attribute("http.status_code", 500)
                    
                    # Record full exception with traceback
                    current_span.record_exception(exc)
                    current_span.set_status(Status(StatusCode.ERROR, str(exc)))
            except Exception:
                pass  # Don't fail if tracing fails
        
        logger.error("Unexpected error: %s", exc)
        logger.error("Traceback: %s", traceback.format_exc())

        error_detail = ErrorDetail(
            message="Internal server error",
            code="INTERNAL_ERROR",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()},
        )



