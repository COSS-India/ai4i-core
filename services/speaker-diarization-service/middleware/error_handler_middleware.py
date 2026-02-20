"""
Global error handler middleware for consistent error responses.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError, 
    RateLimitExceededError,
    InvalidAPIKeyError,
    ExpiredAPIKeyError,
    ErrorDetail
)
import logging
import re
import time
import traceback

# Import OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

logger = logging.getLogger(__name__)


def _strip_status_prefix(message: str) -> str:
    """
    Remove leading HTTP status codes like '403: ' from error messages so that
    user-facing messages match API Gateway (which does not include status
    codes in the message text).
    """
    if not isinstance(message, str):
        return message
    # Match patterns like "403: something" or "401 : something"
    match = re.match(r"^\s*(\d{3})\s*:\s*(.+)$", message)
    if match:
        return match.group(2)
    return message


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(InvalidAPIKeyError)
    async def invalid_api_key_error_handler(request: Request, exc: InvalidAPIKeyError):
        """Handle invalid API key errors, including missing API keys."""
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
        
        # Also check if the error message indicates missing API key (fallback check)
        error_msg = getattr(exc, "message", None) or str(exc.detail) if hasattr(exc, "detail") else str(exc)
        if "missing" in error_msg.lower():
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )
        
        # Strip status code prefix from error message
        clean_message = _strip_status_prefix(error_msg)
        
        # For invalid API key errors, return AUTHORIZATION_ERROR format (matching gateway)
        return JSONResponse(
            status_code=401,
            content={
                "detail": {
                    "error": "AUTHORIZATION_ERROR",
                    "message": clean_message,
                }
            },
        )
    
    @app.exception_handler(ExpiredAPIKeyError)
    async def expired_api_key_error_handler(request: Request, exc: ExpiredAPIKeyError):
        """Handle expired API key errors."""
        error_detail = ErrorDetail(
            message=exc.message,
            code="EXPIRED_API_KEY",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=401,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        # PRIORITY 1: Check if no API key header is provided FIRST - return API_KEY_MISSING
        # This handles cases where the error message might not be extracted correctly
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
        
        # Capture original message for ownership checks (after header check)
        error_msg = (
            getattr(exc, "message", None)
            or (str(exc.detail) if hasattr(exc, "detail") and exc.detail else "")
        )
        error_msg = _strip_status_prefix(error_msg) if error_msg else ""
        
        # Get raw headers for BOTH mode detection
        raw_headers = {k.lower(): v for k, v in request.headers.items()}
        authorization_provided = "authorization" in raw_headers
        
        # PRIORITY 2: For the ownership case, return explicit error + message fields with AUTHORIZATION_ERROR
        # This must be checked BEFORE "Invalid API key" check
        # Check both the message attribute and detail to ensure we catch it
        ownership_msg = "API key does not belong to the authenticated user"
        exc_detail_str = str(exc.detail) if hasattr(exc, "detail") and exc.detail else ""
        if ownership_msg in (error_msg or "") or ownership_msg in exc_detail_str:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": ownership_msg,
                    }
                },
            )
        
        # PRIORITY 3: For invalid API key errors in BOTH mode, check if we have Bearer token
        # If we have Bearer token (BOTH mode) and error is about invalid API key, it's likely ownership
        if "Invalid API key" in (error_msg or ""):
            has_bearer_token = authorization_provided and raw_headers.get("authorization", "").startswith("Bearer ")
            # In BOTH mode, if we have JWT token and API key validation fails, it's ownership issue
            if has_bearer_token:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "error": "AUTHORIZATION_ERROR",
                            "message": ownership_msg,
                        }
                    },
                )
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
        # return standard authentication error format
        error_detail = ErrorDetail(
            message=error_msg or exc.message,
            code="AUTHENTICATION_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=401,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
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
        
        # Also check if the error message indicates missing API key (fallback check)
        error_msg = getattr(exc, "message", None) or str(exc.detail) if hasattr(exc, "detail") else str(exc)
        if "missing" in error_msg.lower():
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )
        
        # Strip status code prefix from error message (e.g., "403: Invalid API key" -> "Invalid API key")
        clean_message = _strip_status_prefix(error_msg)
        
        # For invalid API key errors, return AUTHORIZATION_ERROR format
        if "Invalid API key" in clean_message or "invalid api key" in clean_message.lower():
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": clean_message,
                    }
                },
            )
        
        # For other authorization errors, return standard format
        error_detail = ErrorDetail(
            message=clean_message,
            code="AUTHORIZATION_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=403,
            content={"detail": error_detail.dict()}
        )

    """
 # Preserve structured details from upstream services when possible
        detail_val = getattr(exc, "detail", None)
        if isinstance(detail_val, dict):
            # API Gateway style: {"error": "...", "message": "..."}
            if "error" in detail_val and "message" in detail_val:
                return JSONResponse(status_code=exc.status_code, content={"detail": {"error": detail_val.get("error"), "message": detail_val.get("message")}})
            # ErrorDetail style: {"code": "...", "message": "..."}
            if "code" in detail_val and "message" in detail_val:
                return JSONResponse(status_code=exc.status_code, content={"detail": {"code": detail_val.get("code"), "message": detail_val.get("message")}})

        # If it's a Pydantic model, convert to dict
        try:
            if hasattr(detail_val, "dict"):
                detail_dict = detail_val.dict()
                return JSONResponse(status_code=exc.status_code, content={"detail": detail_dict})
        except Exception:
            pass

        # Fall back to using attributes if present
        error_code = getattr(exc, "error_code", None) or getattr(exc, "code", None) or "HTTP_ERROR"
        error_message = getattr(exc, "message", None) or (str(detail_val) if detail_val is not None else str(exc))
        """
        
    
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
        
        error_msg = str(exc.detail) if exc.detail else ""
        if "missing" in error_msg.lower():
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "API_KEY_MISSING",
                        "message": "API key is required to access this service.",
                    }
                },
            )
        
        # Strip status code prefix from error message
        clean_message = _strip_status_prefix(error_msg)
        
        # For invalid API key errors, return AUTHORIZATION_ERROR format
        if "Invalid API key" in clean_message or "invalid api key" in clean_message.lower():
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": clean_message,
                    }
                },
            )
        
        error_detail = ErrorDetail(
            message=clean_message,
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
        elif isinstance(actual_exc, InvalidAPIKeyError):
            return await invalid_api_key_error_handler(request, actual_exc)
        elif isinstance(actual_exc, ExpiredAPIKeyError):
            return await expired_api_key_error_handler(request, actual_exc)
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
