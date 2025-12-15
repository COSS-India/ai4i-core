"""
Global error handler middleware for consistent OCR error responses.

Copied from NMT service to keep behavior and structure consistent.
"""

import logging
import time
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ai4icore_auth import (
    AuthenticationError,
    AuthorizationError,
    ErrorDetail,
    RateLimitExceededError,
)

logger = logging.getLogger(__name__)


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


