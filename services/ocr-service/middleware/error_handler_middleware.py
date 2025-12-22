"""
Global error handler middleware for consistent OCR error responses.

Copied from NMT service to keep behavior and structure consistent.
"""

import logging
import time
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from ai4icore_logging import get_correlation_id, get_logger

from middleware.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ErrorDetail,
    RateLimitExceededError,
)

logger = get_logger(__name__)


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ):  # type: ignore[unused-argument]
        """Handle authentication errors."""
        error_detail = ErrorDetail(
            message=exc.message,
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
        error_detail = ErrorDetail(
            message=exc.message,
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

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle request validation errors (422 Unprocessable Entity)."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get correlation ID if available
        correlation_id = get_correlation_id(request)
        
        # Build error messages
        error_messages = []
        for error in exc.errors():
            loc = ".".join(map(str, error["loc"]))
            error_messages.append(f"{loc}: {error['msg']}")
        
        full_message = f"Validation error: {'; '.join(error_messages)}"
        
        # Log the validation error explicitly with trace_id
        # This ensures 422 errors are logged even if middleware doesn't catch them
        log_context = {
            "method": method,
            "path": path,
            "status_code": 422,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "validation_errors": exc.errors(),
        }
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        
        # Log the validation error explicitly with trace_id
        # This ensures 422 errors are logged even if middleware doesn't catch them
        # Use logger.warning to match RequestLoggingMiddleware behavior for 4xx errors
        # IMPORTANT: This handler MUST log because RequestLoggingMiddleware might not catch 422 responses
        logger.warning(
            f"{method} {path} - 422 - Validation error: {full_message}",
            extra={"context": log_context}
        )
        
        error_detail = ErrorDetail(
            message="Validation error",
            code="VALIDATION_ERROR",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
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


