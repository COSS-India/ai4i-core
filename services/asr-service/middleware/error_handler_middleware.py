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
import logging
import time
import traceback

# Import OpenTelemetry for tracing
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer("asr-service")


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authentication")
                reject_span.set_attribute("auth.rejected", True)
                reject_span.set_attribute("error.type", "AuthenticationError")
                reject_span.set_attribute("error.reason", "authentication_failed")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", "AUTHENTICATION_ERROR")
                reject_span.set_attribute("http.status_code", 401)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
        
        error_detail = ErrorDetail(
            message=exc.message,
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
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authorization")
                reject_span.set_attribute("auth.rejected", True)
                reject_span.set_attribute("error.type", "AuthorizationError")
                reject_span.set_attribute("error.reason", "authorization_failed")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", "AUTHORIZATION_ERROR")
                reject_span.set_attribute("http.status_code", 403)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
        
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
    
    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        """Handle service-specific errors with Jaeger tracing."""
        # Record error in Jaeger span
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
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
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.code", "HTTP_ERROR")
                current_span.set_attribute("error.message", str(exc.detail))
                current_span.set_attribute("http.status_code", exc.status_code)
                current_span.set_status(Status(StatusCode.ERROR, str(exc.detail)))
        except Exception:
            pass
        
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
        logger.error(f"Unexpected error: {exc}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Record error in Jaeger span
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.code", "INTERNAL_ERROR")
                current_span.set_attribute("error.message", str(exc))
                current_span.set_attribute("error.type", type(exc).__name__)
                current_span.set_attribute("http.status_code", 500)
                current_span.record_exception(exc)
                current_span.set_status(Status(StatusCode.ERROR, str(exc)))
        except Exception:
            pass
        
        error_detail = ErrorDetail(
            message="Internal server error",
            code="INTERNAL_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
