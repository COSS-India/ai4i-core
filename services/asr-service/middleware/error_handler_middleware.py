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
    ServiceError,
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    AudioProcessingError
)
from services.constants.error_messages import (
    AUTH_FAILED,
    AUTH_FAILED_MESSAGE,
    RATE_LIMIT_EXCEEDED,
    RATE_LIMIT_EXCEEDED_MESSAGE,
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_MESSAGE
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
        error_detail = ErrorDetail(
            message=AUTH_FAILED_MESSAGE,
            code=AUTH_FAILED
        )
        return JSONResponse(
            status_code=401,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
        error_detail = ErrorDetail(
            message=exc.message,
            code="AUTHORIZATION_ERROR"
        )
        return JSONResponse(
            status_code=403,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitExceededError):
        """Handle rate limit exceeded errors."""
        # Format message with retry_after value
        message = RATE_LIMIT_EXCEEDED_MESSAGE.format(x=exc.retry_after)
        error_detail = ErrorDetail(
            message=message,
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
        # Record error in Jaeger span
        if TRACING_AVAILABLE:
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
            code=exc.error_code
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle generic HTTP exceptions."""
        # Record error in Jaeger span (dev code)
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.code", "HTTP_ERROR")
                    current_span.set_attribute("error.message", str(exc.detail))
                    current_span.set_attribute("http.status_code", exc.status_code)
                    current_span.set_status(Status(StatusCode.ERROR, str(exc.detail)))
            except Exception:
                pass  # Don't fail if tracing fails
        
        # Map status codes to error constants (our changes)
        status_code = exc.status_code
        error_code = None
        error_message = str(exc.detail)
        
        # Check if detail is already an ErrorDetail dict (from routers)
        if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
            # Already formatted as ErrorDetail, return as-is
            return JSONResponse(
                status_code=status_code,
                content={"detail": exc.detail}
            )
        
        # Map common status codes to error constants
        if status_code == 503:
            error_code = SERVICE_UNAVAILABLE
            error_message = SERVICE_UNAVAILABLE_MESSAGE
        elif status_code == 400:
            error_code = INVALID_REQUEST
            error_message = INVALID_REQUEST_MESSAGE
        elif status_code == 401:
            error_code = AUTH_FAILED
            error_message = AUTH_FAILED_MESSAGE
        elif status_code == 500:
            # For 500 errors, preserve the actual error message from logs
            error_code = "INTERNAL_SERVER_ERROR"
            # Keep the actual error message from exc.detail
            error_message = error_message
        else:
            # For unmapped errors, use the detail as message and generate a code
            error_code = f"HTTP_{status_code}_ERROR"
        
        error_detail = ErrorDetail(
            message=error_message,
            code=error_code
        )
        return JSONResponse(
            status_code=status_code,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        # Log the full error with traceback
        error_message = str(exc)
        logger.error(f"Unexpected error: {exc}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Record error in Jaeger span (dev code)
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.code", "INTERNAL_ERROR")
                    current_span.set_attribute("error.message", str(exc))
                    current_span.set_attribute("error.type", type(exc).__name__)
                    current_span.set_attribute("http.status_code", 500)
                    current_span.record_exception(exc)
                    current_span.set_status(Status(StatusCode.ERROR, str(exc)))
            except Exception:
                pass  # Don't fail if tracing fails
        
        # Preserve the actual error message from the exception (our changes)
        error_detail = ErrorDetail(
            message=error_message,  # Use actual error message from exception
            code="INTERNAL_SERVER_ERROR"
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
