"""
Global error handler middleware for consistent error responses.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError, 
    RateLimitExceededError,
    ErrorDetail
)
import logging
import time
import traceback

import os

try:
    from ai4icore_logging import get_logger, get_correlation_id
    logger = get_logger(__name__)
    LOGGING_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    LOGGING_AVAILABLE = False
    
    def get_correlation_id(request: Request) -> str:
        """Fallback correlation ID getter."""
        return getattr(request.state, 'correlation_id', None) or request.headers.get('x-correlation-id', 'unknown')

# Import OpenTelemetry to extract trace_id
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

# Get Jaeger URL from environment or use default
JAEGER_UI_URL = os.getenv("JAEGER_UI_URL", "http://localhost:16686")


def _log_error_to_opensearch(request: Request, status_code: int, error_code: str, error_message: str):
    """Helper function to log errors to OpenSearch in RequestLoggingMiddleware format."""
    method = request.method
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    user_id = getattr(request.state, "user_id", None)
    api_key_id = getattr(request.state, "api_key_id", None)
    correlation_id = get_correlation_id(request)
    
    # Extract trace_id from OpenTelemetry context for Jaeger URL
    trace_id = None
    jaeger_trace_url = None
    if TRACING_AVAILABLE:
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.get_span_context().is_valid:
                span_context = current_span.get_span_context()
                # Format trace_id as hex string (Jaeger format)
                trace_id = format(span_context.trace_id, '032x')
                # Create full Jaeger URL
                jaeger_trace_url = f"{JAEGER_UI_URL}/trace/{trace_id}"
        except Exception:
            # If trace extraction fails, continue without it
            pass
    
    log_context = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": 0.0,
        "client_ip": client_ip,
        "user_agent": user_agent,
        "error_code": error_code,
    }
    
    if user_id:
        log_context["user_id"] = user_id
    if api_key_id:
        log_context["api_key_id"] = api_key_id
    if correlation_id:
        log_context["correlation_id"] = correlation_id
    if trace_id:
        log_context["trace_id"] = trace_id
    if jaeger_trace_url:
        log_context["jaeger_trace_url"] = jaeger_trace_url
    
    if LOGGING_AVAILABLE:
        if 400 <= status_code < 500:
            logger.warning(
                f"{method} {path} - {status_code} - 0.000s",
                extra={"context": log_context}
            )
        else:
            logger.error(
                f"{method} {path} - {status_code} - 0.000s",
                extra={"context": log_context}
            )
    else:
        if 400 <= status_code < 500:
            logger.warning(f"{method} {path} - {status_code} - {error_message}")
        else:
            logger.error(f"{method} {path} - {status_code} - {error_message}")


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        # Log to OpenSearch
        _log_error_to_opensearch(request, 401, "AUTHENTICATION_ERROR", exc.message)
        
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
        # Log to OpenSearch
        _log_error_to_opensearch(request, 403, "AUTHORIZATION_ERROR", exc.message)
        
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
        # Log to OpenSearch
        _log_error_to_opensearch(request, 429, "RATE_LIMIT_EXCEEDED", exc.message)
        
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
        # Log the error to OpenSearch (similar to RequestLoggingMiddleware)
        # This is important because exception handler responses might bypass RequestLoggingMiddleware
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        correlation_id = get_correlation_id(request)
        
        # Extract trace_id from OpenTelemetry context for Jaeger URL
        trace_id = None
        jaeger_trace_url = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    span_context = current_span.get_span_context()
                    trace_id = format(span_context.trace_id, '032x')
                    jaeger_trace_url = f"{JAEGER_UI_URL}/trace/{trace_id}"
            except Exception:
                pass
        
        # Extract error information from detail (handle API Gateway format)
        error_code = "HTTP_ERROR"
        error_message = str(exc.detail)
        
        if isinstance(exc.detail, dict):
            # Handle API Gateway format: {"error": "AUTHENTICATION_REQUIRED", "message": "..."}
            if "error" in exc.detail:
                error_code = exc.detail.get("error", "HTTP_ERROR")
                error_message = exc.detail.get("message", str(exc.detail))
            # Handle ErrorDetail format: {"code": "...", "message": "..."}
            elif "code" in exc.detail:
                error_code = exc.detail.get("code", "HTTP_ERROR")
                error_message = exc.detail.get("message", str(exc.detail))
        
        # Build log context matching RequestLoggingMiddleware format
        log_context = {
            "method": method,
            "path": path,
            "status_code": exc.status_code,
            "duration_ms": 0.0,  # Approximate for errors
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_code": error_code,
            "error_message": error_message,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        if trace_id:
            log_context["trace_id"] = trace_id
        if jaeger_trace_url:
            log_context["jaeger_trace_url"] = jaeger_trace_url
        
        # Log with appropriate level
        if LOGGING_AVAILABLE:
            if 400 <= exc.status_code < 500:
                logger.warning(
                    f"{method} {path} - {exc.status_code} - 0.000s",
                    extra={"context": log_context}
                )
            else:
                logger.error(
                    f"{method} {path} - {exc.status_code} - 0.000s",
                    extra={"context": log_context}
                )
        else:
            if 400 <= exc.status_code < 500:
                logger.warning(f"{method} {path} - {exc.status_code} - {error_message}")
            else:
                logger.error(f"{method} {path} - {exc.status_code} - {error_message}")
        
        # Check if detail is already a structured dict (preserve API Gateway format or ErrorDetail format)
        if isinstance(exc.detail, dict):
            # Preserve structured error details if they exist (API Gateway format or ErrorDetail format)
            if "error" in exc.detail or "code" in exc.detail or "message" in exc.detail:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail}
                )
        
        # Otherwise, wrap in ErrorDetail
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
        """Handle unexpected exceptions."""
        # Log the error to OpenSearch (similar to RequestLoggingMiddleware)
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        correlation_id = get_correlation_id(request)
        
        # Extract trace_id from OpenTelemetry context for Jaeger URL
        trace_id = None
        jaeger_trace_url = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    span_context = current_span.get_span_context()
                    trace_id = format(span_context.trace_id, '032x')
                    jaeger_trace_url = f"{JAEGER_UI_URL}/trace/{trace_id}"
            except Exception:
                pass
        
        # Build log context matching RequestLoggingMiddleware format
        log_context = {
            "method": method,
            "path": path,
            "status_code": 500,
            "duration_ms": 0.0,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_code": "INTERNAL_ERROR",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        if trace_id:
            log_context["trace_id"] = trace_id
        if jaeger_trace_url:
            log_context["jaeger_trace_url"] = jaeger_trace_url
        
        # Log error with full context
        if LOGGING_AVAILABLE:
            logger.error(
                f"{method} {path} - 500 - 0.000s",
                extra={"context": log_context},
                exc_info=True
            )
        else:
            logger.error(f"Unexpected error: {exc}", exc_info=True)
        
        error_detail = ErrorDetail(
            message="Internal server error",
            code="INTERNAL_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors."""
        # Log to OpenSearch (validation errors happen during body parsing, before route handler)
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        correlation_id = get_correlation_id(request)
        
        # Extract trace_id from OpenTelemetry context for Jaeger URL
        trace_id = None
        jaeger_trace_url = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    span_context = current_span.get_span_context()
                    trace_id = format(span_context.trace_id, '032x')
                    jaeger_trace_url = f"{JAEGER_UI_URL}/trace/{trace_id}"
            except Exception:
                pass
        
        # Build error message
        error_messages = [f"{err.get('loc', [])}: {err.get('msg', '')}" for err in exc.errors()]
        full_message = "; ".join(error_messages)
        
        # Build log context matching RequestLoggingMiddleware format
        log_context = {
            "method": method,
            "path": path,
            "status_code": 422,
            "duration_ms": 0.001,  # Minimal time for validation errors
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_code": "VALIDATION_ERROR",
            "validation_errors": exc.errors(),
            "validation_error_count": len(exc.errors()),
            "validation_error_message": full_message,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        if trace_id:
            log_context["trace_id"] = trace_id
        if jaeger_trace_url:
            log_context["jaeger_trace_url"] = jaeger_trace_url
        
        # Log with WARNING level (4xx errors)
        if LOGGING_AVAILABLE:
            logger.warning(
                f"{method} {path} - 422 - 0.001s",
                extra={"context": log_context}
            )
        else:
            logger.warning(f"Validation error at {path}: {full_message}")
        
        errors = []
        for err in exc.errors():
            errors.append({
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", "")
            })
        return JSONResponse(status_code=422, content={"detail": errors})

