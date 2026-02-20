"""
Global error handler middleware for consistent error responses.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError, 
    RateLimitExceededError,
    ErrorDetail
)
import logging
import time
import traceback
import re

# NOTE:
# Unlike ASR/API Gateway containers, audio-lang-detection's Docker image only copies this
# service directory into /app, so the shared `services.constants` package
# is not available at runtime. To keep the same user-facing message for
# expired/invalid tokens, we duplicate the constant value here.
AUTH_FAILED_MESSAGE = "Authentication failed. Please log in again."


def _strip_status_prefix(message: str) -> str:
    """
    Remove leading HTTP status codes like '403: ' from error messages so that
    user-facing messages match API Gateway (which does not include status
    codes in the message text).
    """
    if not isinstance(message, str):
        return message
    # Match patterns like "403: something" or "401 : something"
    m = re.match(r"^\s*(\d{3})\s*:\s*(.+)$", message)
    if m:
        return m.group(2)
    return message

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("audio-lang-detection-service")


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors.

        For expired/invalid tokens we want to mirror API Gateway behavior and return
        the same user-facing message (`AUTH_FAILED_MESSAGE`), while still keeping
        the more specific details in tracing/logging.
        """
        # Capture original message for tracing and ownership checks
        error_msg = (
            getattr(exc, "message", None)
            or (str(exc.detail) if hasattr(exc, "detail") and exc.detail else "")
        )

        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authentication")
                reject_span.set_attribute("auth.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "AuthenticationError")
                reject_span.set_attribute("error.reason", "authentication_failed")
                # Record the low-level message for debugging
                reject_span.set_attribute("error.message", error_msg or exc.message)
                reject_span.set_attribute("error.code", "AUTHENTICATION_ERROR")
                reject_span.set_attribute("http.status_code", 401)
                reject_span.set_status(
                    Status(StatusCode.ERROR, error_msg or exc.message or AUTH_FAILED_MESSAGE)
                )
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically in parent spans when exception was raised

        # For the ownership case, return explicit error + message fields with AUTHORIZATION_ERROR
        if "API key does not belong to the authenticated user" in (error_msg or ""):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": "API key does not belong to the authenticated user",
                    }
                },
            )

        # For invalid API key errors in BOTH mode, check if it's actually an ownership issue
        # In BOTH mode, when user_id is provided and auth-service returns valid=false,
        # it's an ownership issue even if the message says "does not have access"
        error_msg_lower_check = (error_msg or "").lower()
        if "invalid api key" in error_msg_lower_check:
            # Check if this is BOTH mode (request has Authorization header with Bearer token)
            # and the error is about access - in BOTH mode, this means ownership
            authorization_header = request.headers.get("authorization", "")
            is_both_mode = authorization_header.startswith("Bearer ")
            logger.info(f"AuthenticationError handler: error_msg={error_msg}, is_both_mode={is_both_mode}, has_access_error={'does not have access' in error_msg_lower_check}")
            if is_both_mode and "does not have access" in error_msg_lower_check:
                # This is BOTH mode and the error is about access - treat as ownership
                logger.info("Detected ownership error in BOTH mode, returning ownership message")
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "error": "AUTHORIZATION_ERROR",
                            "message": "API key does not belong to the authenticated user",
                        }
                    },
                )
            # Otherwise, it's a regular permission error
            clean_message = _strip_status_prefix(error_msg or "Invalid API key")
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": clean_message,
                    }
                },
            )

        # For missing API key, mirror API Gateway "API_KEY_MISSING" behavior
        if "Missing API key" in (error_msg or ""):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )

        # For token-expired / invalid-token and all other authentication failures,
        # align user-facing message with API Gateway:
        #   "Authentication failed. Please log in again."
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
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authorization")
                reject_span.set_attribute("auth.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "AuthorizationError")
                reject_span.set_attribute("error.reason", "authorization_failed")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", "AUTHORIZATION_ERROR")
                reject_span.set_attribute("http.status_code", 403)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically in parent spans when exception was raised
        
        # Strip any leading HTTP status codes like "403: " from the message
        # to match API Gateway format (which does not include status codes in messages)
        message = _strip_status_prefix(exc.message)
        message_lower = message.lower()
        
        # Check if this is an ownership error - in BOTH mode, permission errors are actually ownership
        # Check if we're in BOTH mode (has Bearer token in Authorization header)
        authorization_header = request.headers.get("authorization", "")
        is_both_mode = authorization_header.startswith("Bearer ")
        
        # Ownership detection: explicit ownership message OR (BOTH mode + permission error)
        # In BOTH mode, any "Invalid API key" error with "does not have access" is an ownership issue
        is_ownership = (
            "does not belong" in message_lower
            or "ownership" in message_lower
            or (is_both_mode and "invalid api key" in message_lower and ("does not have access" in message_lower or "does not belong" in message_lower))
        )
        
        if is_ownership:
            # This is an ownership issue - return ownership message
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": "API key does not belong to the authenticated user",
                    }
                },
            )
        
        error_detail = ErrorDetail(
            message=message,
            code="AUTHORIZATION_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=403,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitExceededError):
        """Handle rate limit exceeded errors."""
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("rate_limit.operation", "reject_rate_limit")
                reject_span.set_attribute("rate_limit.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "RateLimitExceededError")
                reject_span.set_attribute("error.reason", "rate_limit_exceeded")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", "RATE_LIMIT_EXCEEDED")
                reject_span.set_attribute("rate_limit.retry_after", exc.retry_after)
                reject_span.set_attribute("http.status_code", 429)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically in parent spans when exception was raised
        
        error_detail = ErrorDetail(
            message=exc.message,
            code="RATE_LIMIT_EXCEEDED",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=429,
            content={"detail": error_detail.dict()},
            headers={"Retry-After": str(exc.retry_after)}
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle generic HTTP exceptions."""
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="HTTP_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        # Extract exception from ExceptionGroup if present (Python 3.11+)
        actual_exc = exc
        try:
            if hasattr(exc, 'exceptions') and exc.exceptions:
                actual_exc = exc.exceptions[0]
        except (AttributeError, IndexError):
            pass
        
        # Check if it's one of our custom exceptions that wasn't caught
        if isinstance(actual_exc, RateLimitExceededError):
            return await rate_limit_error_handler(request, actual_exc)
        elif isinstance(actual_exc, AuthenticationError):
            return await authentication_error_handler(request, actual_exc)
        elif isinstance(actual_exc, AuthorizationError):
            return await authorization_error_handler(request, actual_exc)
        elif isinstance(actual_exc, HTTPException):
            return await http_exception_handler(request, actual_exc)
        
        logger.error(f"Unexpected error: {exc}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        error_detail = ErrorDetail(
            message="Internal server error",
            code="INTERNAL_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
