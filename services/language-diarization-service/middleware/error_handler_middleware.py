"""
Global error handler middleware for consistent error responses.
"""
import os
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

logger = logging.getLogger(__name__)


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
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
