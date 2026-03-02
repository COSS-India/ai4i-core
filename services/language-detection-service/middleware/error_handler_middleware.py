"""
Global error handler middleware for consistent error responses.
"""
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
import re

# Import OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
    tracer = trace.get_tracer("language-detection-service")
except ImportError:
    TRACING_AVAILABLE = False
    tracer = None

# NOTE:
# Unlike ASR/API Gateway containers, language-detection-service's Docker image only copies this
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
        # Check raw headers (case-insensitive) to see if they were actually provided
        raw_headers = {k.lower(): v for k, v in request.headers.items()}
        x_auth_source_provided = "x-auth-source" in raw_headers
        x_api_key_provided = "x-api-key" in raw_headers
        authorization_provided = "authorization" in raw_headers
        
        # Check if API key is truly missing (not in headers and not in Authorization)
        # AND x-auth-source was not explicitly provided (meaning it's using default)
        api_key_missing = (
            not x_api_key_provided and
            not authorization_provided and
            (not x_auth_source_provided or (raw_headers.get("x-auth-source") or "API_KEY").upper() == "API_KEY")
        )
        
        if api_key_missing:
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

        # PRIORITY 3: For invalid API key errors, always surface the actual
        # "Invalid API key" style message from auth-service instead of converting
        # it into an ownership error. This ensures that when an invalid/unknown
        # API key is provided, clients see an "Invalid API key ..." message and
        # not "API key does not belong to the authenticated user".
        error_msg_lower_check = (error_msg or "").lower()
        if "invalid api key" in error_msg_lower_check:
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
        # "Invalid API key: This key does not have access to language-detection service") so they
        # are not prefixed with "Authorization error: Insufficient permission."
        # Also strip any leading HTTP status codes like "403: " from the message.
        message = _strip_status_prefix(exc.message)
        if not (
            "permission" in message.lower()
            or "does not have" in message.lower()
            or "language-detection.inference" in message
            or "language-detection service" in message
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
            # For other AuthenticationErrors, use default auth failure response
            return JSONResponse(
                status_code=401,
                content={"detail": {"error": "AUTHENTICATION_ERROR", "message": error_msg or "Authentication failed"}}
            )
        
        
        # Preserve structured detail when possible
        detail_val = getattr(exc, "detail", None)
        if isinstance(detail_val, dict):
            # API Gateway style: {"error": "...", "message": "..."}
            if "error" in detail_val and "message" in detail_val:
                return JSONResponse(status_code=exc.status_code, content={"detail": {"error": detail_val.get("error"), "message": detail_val.get("message")}})
            # ErrorDetail style: {"code": "...", "message": "..."}
            if "code" in detail_val and "message" in detail_val:
                return JSONResponse(status_code=exc.status_code, content={"detail": {"code": detail_val.get("code"), "message": detail_val.get("message")}})

        # If detail is a Pydantic model, convert to dict and return
        try:
            if hasattr(detail_val, "dict"):
                detail_dict = detail_val.dict()
                return JSONResponse(status_code=exc.status_code, content={"detail": detail_dict})
        except Exception:
            pass

        # Fall back to attributes on exception
        error_code = getattr(exc, "error_code", None) or getattr(exc, "code", None) or "HTTP_ERROR"
        error_message = getattr(exc, "message", None) or (str(detail_val) if detail_val is not None else str(exc))

        error_detail = ErrorDetail(
            message=error_message,
            code=error_code,
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_detail.dict()}
        )

    """
    # If the exception detail is already a structured dict (from upstream services),
        # preserve its structure instead of stringifying it.
        detail_val = getattr(exc, "detail", None)
        if isinstance(detail_val, dict):
            # API Gateway style: {"error": "...", "message": "..."}
            if "error" in detail_val and "message" in detail_val:
                return JSONResponse(status_code=exc.status_code, content={"detail": {"error": detail_val.get("error"), "message": detail_val.get("message")}})
            # ErrorDetail style: {"code": "...", "message": "..."}
            if "code" in detail_val and "message" in detail_val:
                return JSONResponse(status_code=exc.status_code, content={"detail": {"code": detail_val.get("code"), "message": detail_val.get("message")}})

        # If detail is a Pydantic model, convert to dict and return
        try:
            if hasattr(detail_val, "dict"):
                detail_dict = detail_val.dict()
                return JSONResponse(status_code=exc.status_code, content={"detail": detail_dict})
        except Exception:
            pass

        # If the exception object itself exposes message/code attributes, use them
        error_code = getattr(exc, "error_code", None) or getattr(exc, "code", None) or "HTTP_ERROR"
        error_message = getattr(exc, "message", None) or (str(detail_val) if detail_val is not None else str(exc))
        """
    	   	    	    


        


        
    
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
        
        # Capture full exception in trace span
        if TRACING_AVAILABLE:
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
