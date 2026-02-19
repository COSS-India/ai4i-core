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

# Import OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

logger = logging.getLogger(__name__)


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        # Check both message attribute and detail for the ownership error message
        error_msg = getattr(exc, "message", None) or str(exc.detail) if hasattr(exc, "detail") and exc.detail else ""
        
        # For the ownership case, return explicit error + message fields with AUTHORIZATION_ERROR
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

        # For other authentication errors, return structured format
        return JSONResponse(
            status_code=401,
            content={"detail": {"error": "AUTHENTICATION_ERROR", "message": error_msg or "Authentication failed"}}
        )
    
    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
        error_detail = ErrorDetail(
            message=exc.message,
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
