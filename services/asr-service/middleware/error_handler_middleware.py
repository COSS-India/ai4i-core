"""
Global error handler middleware for consistent error responses.


"""
import os
import time
import logging
import traceback
import re

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id, get_logger

from middleware.exceptions import (
    AuthenticationError,
    AuthorizationError,
    RateLimitExceededError,
    ErrorDetail,
    ServiceError,
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    AudioProcessingError,
)
from services.constants.error_messages import (
    AUTH_FAILED,
    AUTH_FAILED_MESSAGE,
    RATE_LIMIT_EXCEEDED,
    RATE_LIMIT_EXCEEDED_MESSAGE,
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_MESSAGE,
)

logger = get_logger(__name__)
tracer = trace.get_tracer("asr-service")


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
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        # Capture original message for tracing and ownership checks
        error_msg = (
            getattr(exc, "message", None)
            or (str(exc.detail) if hasattr(exc, "detail") and exc.detail else "")
        )
        error_msg = _strip_status_prefix(error_msg) if error_msg else ""

        # Check if no API key header is provided first - return API_KEY_MISSING
        # This handles cases where the error message might not be extracted correctly
        x_auth_source = (request.headers.get("x-auth-source") or "API_KEY").upper()
        x_api_key = request.headers.get("x-api-key")
        if not x_api_key and x_auth_source == "API_KEY":
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
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

        # For invalid API key errors (BOTH mode with bad/missing key), mirror API
        # Gateway behavior by surfacing AUTHORIZATION_ERROR with the original message
        if "Invalid API key" in (error_msg or ""):
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

        # For token-expired / invalid-token errors, return AUTHENTICATION_ERROR
        # Check for common token error messages
        error_msg_lower = (error_msg or "").lower()
        if (
            "expired" in error_msg_lower 
            or ("invalid" in error_msg_lower and "token" in error_msg_lower)
            or "Invalid or expired token" in (error_msg or "")
        ):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHENTICATION_ERROR",
                        "message": AUTH_FAILED_MESSAGE,
                    }
                },
            )

        # For all other authentication failures,
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
        # Preserve detailed API key permission messages from auth-service (e.g.,
        # "Invalid API key: This key does not have access to ASR service") so they
        # are not prefixed with a generic authorization message.
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

        # For permission/ownership issues, keep or normalize the message to a clear
        # "Insufficient permission" format instead of prefixing with "Authorization error".
        if (
            "permission" in message.lower()
            or "does not have" in message.lower()
            or "asr.inference" in message
            or "asr service" in message.lower()
            or "pipeline service" in message.lower()
        ):
            # Normalize to the desired format if this is the standard ASR access message
            if "does not have access to asr service" in message.lower():
                message = "Insufficient permission: This key does not have access to ASR service"
            # Handle pipeline service permission errors
            elif "does not have access to pipeline service" in message.lower():
                message = "Insufficient permission: This key does not have access to pipeline service"
            # Also handle cases where the message might be "Invalid API key: This key does not have access to ASR service"
            elif "invalid api key" in message.lower() and "does not have access to asr service" in message.lower():
                message = "Insufficient permission: This key does not have access to ASR service"
            # Handle pipeline service with invalid API key prefix
            elif "invalid api key" in message.lower() and "does not have access to pipeline service" in message.lower():
                message = "Insufficient permission: This key does not have access to pipeline service"
            # Else leave the permission-related message as-is
        else:
            # For non-permission/ownership-related authorization errors, we can keep or
            # lightly prefix the message if needed.
            if "Authorization error" not in message:
                message = f"Authorization error: {message}"

        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authorization")
                reject_span.set_attribute("auth.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "AuthorizationError")
                reject_span.set_attribute("error.reason", "authorization_failed")
                reject_span.set_attribute("error.message", message)
                reject_span.set_attribute("error.code", "AUTHORIZATION_ERROR")
                reject_span.set_attribute("http.status_code", 403)
                reject_span.set_status(Status(StatusCode.ERROR, message))
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically in parent spans when exception was raised
        
        error_detail = ErrorDetail(
            message=message,
            code="AUTHORIZATION_ERROR",
        )
        return JSONResponse(
            status_code=403,
            content={"detail": error_detail.dict()},
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
            message=RATE_LIMIT_EXCEEDED_MESSAGE.format(x=exc.retry_after),
            code=RATE_LIMIT_EXCEEDED
        )
        return JSONResponse(
            status_code=429,
            content={"detail": error_detail.dict()},
            headers={"Retry-After": str(exc.retry_after)}
        )
    
    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        """Handle service-specific errors with Jaeger tracing."""
        if tracer:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.code", exc.error_code)
                    current_span.set_attribute("error.message", exc.message)
                    current_span.set_attribute("error.type", type(exc).__name__)
                    current_span.set_attribute("http.status_code", exc.status_code)
                    
                    if exc.model_name:
                        current_span.set_attribute("error.model", exc.model_name)
                    if exc.service_error:
                        for key, value in exc.service_error.items():
                            current_span.set_attribute(f"error.{key}", str(value))
                    
                    current_span.record_exception(exc)
                    current_span.set_status(Status(StatusCode.ERROR, exc.message))
            except Exception:
                pass  # Don't fail if tracing fails
        
        error_detail = ErrorDetail(
            message=exc.message,
            code=exc.error_code,
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle generic HTTP exceptions."""
        # Record error in Jaeger span
        if tracer:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.code", "HTTP_ERROR")
                    current_span.set_attribute("error.message", str(exc.detail))
                    current_span.set_attribute("http.status_code", exc.status_code)
                    current_span.set_status(Status(StatusCode.ERROR, str(exc.detail)))
            except Exception:
                pass
        
        # Check if detail is already an ErrorDetail dict
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        
        # Safely convert detail to string if it's not already a string or dict
        # This handles cases where an exception object might be passed as detail
        detail_message = exc.detail
        if not isinstance(detail_message, (str, dict)):
            detail_message = str(detail_message) if detail_message else ""

        # Map specific status codes to error constants
        if exc.status_code == 503:
            error_detail = ErrorDetail(
                message=SERVICE_UNAVAILABLE_MESSAGE,
                code=SERVICE_UNAVAILABLE
            )
        elif exc.status_code == 400:
            error_detail = ErrorDetail(
                message=detail_message if detail_message else INVALID_REQUEST_MESSAGE,
                code=INVALID_REQUEST
            )
        elif exc.status_code == 401:
            # Check if this is a token-related error (AuthenticationError might be caught here)
            detail_str = str(detail_message) if detail_message else ""
            detail_str_lower = detail_str.lower()
            if (
                "expired" in detail_str_lower 
                or ("invalid" in detail_str_lower and "token" in detail_str_lower)
                or "Invalid or expired token" in detail_str
            ):
                # Return structured format for token errors
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "error": "AUTHENTICATION_ERROR",
                            "message": AUTH_FAILED_MESSAGE,
                        }
                    },
                )
            error_detail = ErrorDetail(
                message=AUTH_FAILED_MESSAGE,
                code=AUTH_FAILED
            )
        elif exc.status_code == 500:
            # For 500 errors, use the actual error message
            error_detail = ErrorDetail(
                message=detail_message if detail_message else "Internal server error",
                code="INTERNAL_SERVER_ERROR"
            )
        else:
            error_detail = ErrorDetail(
                message=detail_message if detail_message else "An error occurred",
                code="HTTP_ERROR"
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
            logger.error(f"Unexpected error: {exc}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        error_detail = ErrorDetail(
            message=str(exc) if str(exc) else "Internal server error",
            code="INTERNAL_ERROR"
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
