"""
Global error handler middleware for consistent error responses.


"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from middleware.exceptions import (
    AuthenticationError,
    AuthorizationError,
    RateLimitExceededError,
    ErrorDetail,
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
except ImportError:
    TRACING_AVAILABLE = False

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
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
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
            or (str(exc.detail) if hasattr(exc, "detail") and exc.detail else "")
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

        # Invalid API key (e.g., bad key in API_KEY mode)
        if "Invalid API key" in error_msg:
            # If there is no explicit X-API-Key header, treat this like API_KEY_MISSING
            # to match API Gateway behavior when API key is omitted.
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

        # If we are in API_KEY mode (default when X-Auth-Source is absent) and there is
        # no X-API-Key header at all, treat any remaining auth failure as API_KEY_MISSING.
        # This matches API Gateway behavior when a required API key is not provided.
        x_auth_source = (request.headers.get("x-auth-source") or "API_KEY").upper()
        if x_auth_source == "API_KEY" and not request.headers.get("x-api-key"):
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
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
        # Preserve detailed API key permission messages from auth-service (e.g.,
        # "Invalid API key: This key does not have access to LLM service") so they
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
            or "llm.inference" in message
            or "llm service" in message.lower()
        ):
            # Normalize to the desired format if this is the standard LLM access message
            if "does not have access to llm service" in message.lower():
                message = "Insufficient permission: This key does not have access to LLM service"
            # Else leave the permission-related message as-is
        else:
            # For non-permission/ownership-related authorization errors, we can keep or
            # lightly prefix the message if needed.
            if "Authorization error" not in message:
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
        from middleware.exceptions import AuthenticationError
        if isinstance(exc, AuthenticationError):
            # Check for ownership error message
            raw_message = (
                getattr(exc, "message", None)
                or (str(exc.detail) if hasattr(exc, "detail") and exc.detail else "")
                or str(exc)
            )
            error_msg = _strip_status_prefix(raw_message)
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
                content={
                    "detail": {
                        "error": "AUTHENTICATION_ERROR",
                        "message": AUTH_FAILED_MESSAGE,
                    }
                },
            )
        
        # If exc.detail is already structured (dict with code/message) preserve it
        if isinstance(exc.detail, dict):
            msg = exc.detail.get("message") or str(exc.detail)
            code = exc.detail.get("code") or "HTTP_ERROR"
            error_detail = ErrorDetail(message=msg, code=code, timestamp=time.time())
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": error_detail.dict()}
            )

        # If exc.detail is an ErrorDetail-like object, attempt to use its dict()
        try:
            if hasattr(exc.detail, "dict"):
                detail_dict = exc.detail.dict()
                return JSONResponse(status_code=exc.status_code, content={"detail": detail_dict})
        except Exception:
            pass

        # Fallback: stringify the detail
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
