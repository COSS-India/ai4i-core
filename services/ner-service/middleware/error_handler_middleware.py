"""
Global error handler middleware for consistent NER error responses.

Aligned with OCR service and API Gateway so that API key/JWT auth errors
return the same `error` and `message` shapes at service level.
"""

import logging
import os
import re
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

# Match API Gateway generic auth failure text
AUTH_FAILED_MESSAGE = "Authentication failed. Please log in again."


def _strip_status_prefix(message: str) -> str:
    """
    Remove leading HTTP status codes like '403: ' from error messages so that
    user-facing messages match API Gateway (which does not include status
    codes in the message text).
    """
    if not isinstance(message, str):
        return message
    match = re.match(r"^\s*(\d{3})\s*:\s*(.+)$", message)
    if match:
        return match.group(2)
    return message


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ):  # type: ignore[unused-argument]
        """
        Handle authentication errors.

        For API key / JWT problems we mirror API Gateway behavior:
        - Ownership mismatch -> AUTHORIZATION_ERROR + ownership message
        - Invalid API key    -> AUTHORIZATION_ERROR + "Invalid API key"
        - Missing API key    -> API_KEY_MISSING + gateway message text
        - All other auth failures (e.g. expired/invalid token) -> AUTHENTICATION_ERROR
          with standard "Authentication failed. Please log in again."
        """
        # Use message attribute if available, otherwise use detail or str(exc)
        raw_message = (
            getattr(exc, "message", None)
            or getattr(exc, "detail", None)
            or str(exc)
        )
        error_msg = _strip_status_prefix(raw_message)

        # Ownership case: API key does not belong to the authenticated user
        if "API key does not belong to the authenticated user" in error_msg:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": "API key does not belong to the authenticated user",
                    }
                },
            )

        # Invalid API key (e.g., bad key in BOTH/API_KEY mode)
        if "Invalid API key" in error_msg:
            # If there is no explicit X-API-Key header, this usually means the
            # client didn't provide an API key at all (e.g., only Bearer token),
            # which API Gateway treats as API_KEY_MISSING.
            if not request.headers.get("x-api-key"):
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "error": "API_KEY_MISSING",
                            "message": "API key is required to access this service.",
                        }
                    },
                )

            clean_message = error_msg or "Invalid API key"
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": clean_message,
                    }
                },
            )

        # Missing API key: mirror API Gateway "API_KEY_MISSING"
        if "Missing API key" in error_msg:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )

        # Default: token expired/invalid or generic auth failure
        return JSONResponse(
            status_code=401,
            content={
                "detail": {
                    "error": "AUTHENTICATION_ERROR",
                    "message": AUTH_FAILED_MESSAGE,
                }
            },
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        request: Request, exc: AuthorizationError
    ):  # type: ignore[unused-argument]
        """Handle authorization errors."""
        # Use message attribute if available, otherwise use detail or str(exc)
        message_raw = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        message = _strip_status_prefix(message_raw)

        # If we see an "Invalid API key" authorization error and there is no explicit
        # X-API-Key header, treat this like API_KEY_MISSING to match API Gateway.
        if "invalid api key" in message.lower() and not request.headers.get("x-api-key"):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )

        # Error message should already be formatted by validate_api_key_permissions.
        # For API key permission/ownership issues (e.g., NER), keep the original message
        # from auth-service without prefixing it with "Authorization error: ...".
        if (
            "permission" in message.lower()
            or "does not have" in message.lower()
            or "ner.inference" in message
            or "api key does not belong to the authenticated user" in message.lower()
        ):
            # Examples:
            # - "Invalid API key: This key does not have access to NER service"
            # - "API key does not belong to the authenticated user"
            pass
        else:
            # For other authorization errors, ensure we include a clear prefix
            if "Authorization error" not in message:
                message = f"Authorization error: {message}"

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
        
        # Check if health/metrics logs should be excluded
        exclude_health_logs = os.getenv("EXCLUDE_HEALTH_LOGS", "false").lower() == "true"
        exclude_metrics_logs = os.getenv("EXCLUDE_METRICS_LOGS", "false").lower() == "true"
        
        path = request.url.path.lower().rstrip('/')
        should_skip = False
        if exclude_health_logs and ('/health' in path or path.endswith('/health')):
            should_skip = True
        if exclude_metrics_logs and ('/metrics' in path or path.endswith('/metrics')):
            should_skip = True
        
        if not should_skip:
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



