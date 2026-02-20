"""
Global error handler middleware for consistent error responses.
"""
import os
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError, 
    RateLimitExceededError,
    ErrorDetail
)
import logging
import time
import traceback
import json

# OpenTelemetry imports
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    tracer = trace.get_tracer("language-diarization-service")
    TRACING_AVAILABLE = True
except ImportError:
    tracer = None
    TRACING_AVAILABLE = False

# NOTE:
# Unlike ASR/API Gateway containers, language-diarization-service's Docker image only copies this
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

        # PRIORITY 1: Check if no API key header is provided - return API_KEY_MISSING
        # Match NMT/OCR pattern: simple check for missing headers
        x_auth_source = (request.headers.get("x-auth-source") or "API_KEY").upper()
        x_api_key = request.headers.get("x-api-key")
        authorization = request.headers.get("authorization", "")
        
        # If x-api-key is not provided and no authorization header with API key, and auth_source is API_KEY
        if not x_api_key and x_auth_source == "API_KEY" and not authorization.startswith("ApiKey "):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )

        # PRIORITY 2: For the ownership case, return explicit error + message fields with AUTHORIZATION_ERROR
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

        # PRIORITY 3: For invalid API key errors in BOTH mode, check if it's actually an ownership issue
        # This matches language-detection / OCR / NMT behavior.
        error_msg_lower_check = (error_msg or "").lower()
        if "invalid api key" in error_msg_lower_check:
            # Check if this is BOTH mode (request has Authorization header with Bearer token)
            authorization_header = request.headers.get("authorization", "")
            is_both_mode = authorization_header.startswith("Bearer ")

            # In BOTH mode, when auth-service returns
            #   "Invalid API key: This key does not have access to LANGUAGE_DIARIZATION service"
            # for a key that belongs to a **different** user, we want to surface it as an
            # ownership problem, not a permission problem – same as other services.
            if is_both_mode and "does not have access" in error_msg_lower_check:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "error": "AUTHORIZATION_ERROR",
                            "message": "API key does not belong to the authenticated user",
                        }
                    },
                )

            # Otherwise (non‑BOTH mode or other invalid‑key messages), treat it as a
            # regular permission error and preserve the original message.
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

        # PRIORITY 4: For missing API key in message, mirror API Gateway "API_KEY_MISSING" behavior
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
        
        # Preserve detailed API key permission messages from auth-service (e.g.,
        # "Invalid API key: This key does not have access to language-diarization service") so they
        # are not prefixed with "Authorization error: Insufficient permission."
        # Also strip any leading HTTP status codes like "403: " from the message.
        message = _strip_status_prefix(exc.message)
        if not (
            "permission" in message.lower()
            or "does not have" in message.lower()
            or "language-diarization.inference" in message
            or "language-diarization service" in message
        ):
            # For non-permission-related authorization errors, keep a clear prefix
            if not message.startswith("Authorization error"):
                message = f"Authorization error: {message}"

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
        # PRIORITY 1: Check if no API key header is provided FIRST - return API_KEY_MISSING
        # Match NMT/OCR pattern: simple check for missing headers
        x_auth_source = (request.headers.get("x-auth-source") or "API_KEY").upper()
        x_api_key = request.headers.get("x-api-key")
        authorization = request.headers.get("authorization", "")
        
        # If x-api-key is not provided and no authorization header with API key, and auth_source is API_KEY
        if not x_api_key and x_auth_source == "API_KEY" and not authorization.startswith("ApiKey "):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )
        
        # Handle AuthenticationError here if it wasn't caught by the specific handler
        if isinstance(exc, AuthenticationError):
            # Check for ownership error message
            error_msg = getattr(exc, "message", None) or str(exc.detail) if hasattr(exc, "detail") and exc.detail else ""
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
            # Check for missing API key in message
            if "missing" in error_msg.lower() and "api key" in error_msg.lower():
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "error": "API_KEY_MISSING",
                            "message": "API key is required to access this service.",
                        }
                    },
                )
            # For other AuthenticationErrors, use default auth failure response
            return JSONResponse(
                status_code=401,
                content={"detail": {"error": "AUTHENTICATION_ERROR", "message": error_msg or "Authentication failed"}}
            )
        
        error_msg = str(exc.detail) if exc.detail else ""
        # Check for missing API key in message
        if "missing" in error_msg.lower() and "api key" in error_msg.lower():
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )
        
        error_detail = ErrorDetail(
            message=error_message,
            code=error_code,
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions with detailed logging and tracing."""
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
        
        # Get full traceback for logging
        tb_str = traceback.format_exc()
        
        # Extract request details for better debugging
        request_details = {
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "client_host": request.client.host if request.client else "unknown",
            "headers": dict(request.headers),
        }
        
        # Try to extract request body (be careful with large bodies)
        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                # This might fail if body was already consumed
                body = await request.body()
                if len(body) < 10000:  # Only log if < 10KB
                    try:
                        request_details["body"] = json.loads(body)
                    except Exception:
                        request_details["body"] = body.decode('utf-8', errors='ignore')[:1000]
        except Exception:
            pass
        
        # Check if health/metrics logs should be excluded
        exclude_health_logs = os.getenv("EXCLUDE_HEALTH_LOGS", "false").lower() == "true"
        exclude_metrics_logs = os.getenv("EXCLUDE_METRICS_LOGS", "false").lower() == "true"
        
        path = request.url.path.lower().rstrip('/')
        should_skip = False
        if exclude_health_logs and ('/health' in path or path.endswith('/health')):
            should_skip = True
        if exclude_metrics_logs and ('/metrics' in path or path.endswith('/metrics')):
            should_skip = True
        
        # Enhanced error logging with request context (skip if health/metrics)
        if not should_skip:
            logger.error(
                "Unexpected error in %s %s: %s\nRequest details: %s\nTraceback:\n%s",
                request.method,
                request.url.path,
                str(exc),
                json.dumps(request_details, indent=2, default=str),
                tb_str
            )
        
        # Add error details to tracing span if available
        if tracer:
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(actual_exc).__name__)
                span.set_attribute("error.message", str(actual_exc))
                span.set_attribute("http.status_code", 500)
                span.set_attribute("error.stack_trace", tb_str)
                span.add_event("exception.occurred", {
                    "exception.type": type(actual_exc).__name__,
                    "exception.message": str(actual_exc),
                    "exception.stacktrace": tb_str[:1000],  # Truncate for span
                    "request.method": request.method,
                    "request.path": request.url.path
                })
                span.set_status(Status(StatusCode.ERROR, str(actual_exc)))
                span.record_exception(actual_exc)
        
        error_detail = ErrorDetail(
            message="Internal server error",
            code="INTERNAL_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
