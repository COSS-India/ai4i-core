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

# Import OpenTelemetry to extract trace_id and create spans
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
    tracer = trace.get_tracer("pipeline-service")
except ImportError:
    TRACING_AVAILABLE = False
    tracer = None

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
                # Store only trace_id - OpenSearch will use URL template to construct full URL
                jaeger_trace_url = trace_id
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


async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """Handle authentication errors."""
    # Get message from exc.message or exc.detail (HTTPException uses detail)
    error_message = getattr(exc, 'message', None) or str(exc.detail) if hasattr(exc, 'detail') else str(exc)
    
    if tracer:
        with tracer.start_as_current_span("request.reject") as reject_span:
            reject_span.set_attribute("auth.operation", "reject_authentication")
            reject_span.set_attribute("auth.rejected", True)
            # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
            reject_span.set_attribute("http.method", request.method)
            reject_span.set_attribute("http.path", request.url.path)
            reject_span.set_attribute("http.status_code", 401)
            reject_span.set_attribute("error.code", "AUTHENTICATION_ERROR")
            reject_span.set_attribute("error.message", error_message)
            
            # Add correlation ID if available
            correlation_id = get_correlation_id(request)
            if correlation_id:
                reject_span.set_attribute("correlation.id", correlation_id)
            
            reject_span.set_status(Status(StatusCode.ERROR, error_message))
            reject_span.record_exception(exc)
    
    # Check if this is a JWT authentication failure (should return AUTH_FAILED)
    jwt_failure_messages = [
        "Authentication failed. Please log in again.",
        "Invalid or expired token",
        "Missing bearer token",
        "Invalid token type",
        "User ID not found in token",
        "Failed to verify token"
    ]
    
    is_jwt_failure = any(msg in error_message for msg in jwt_failure_messages)
    error_code = "AUTH_FAILED" if is_jwt_failure else "AUTHENTICATION_ERROR"
    
    # Log to OpenSearch
    _log_error_to_opensearch(request, 401, error_code, error_message)
    
    error_detail = ErrorDetail(
        message=error_message,
        code=error_code,
        timestamp=time.time()
    )
    # Exclude timestamp from response
    try:
        detail_dict = error_detail.model_dump(exclude={'timestamp'}) if hasattr(error_detail, 'model_dump') else error_detail.dict(exclude={'timestamp'})
    except Exception:
        detail_dict = error_detail.dict(exclude={'timestamp'})
    return JSONResponse(
        status_code=401,
        content={"detail": detail_dict}
    )


async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """Handle authentication errors."""
    # Get message from exc.message or exc.detail (HTTPException uses detail)
    error_message = getattr(exc, 'message', None) or str(exc.detail) if hasattr(exc, 'detail') else str(exc)
    
    if tracer:
        with tracer.start_as_current_span("request.reject") as reject_span:
            reject_span.set_attribute("auth.operation", "reject_authentication")
            reject_span.set_attribute("auth.rejected", True)
            # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
            reject_span.set_attribute("http.method", request.method)
            reject_span.set_attribute("http.path", request.url.path)
            reject_span.set_attribute("http.status_code", 401)
            reject_span.set_attribute("error.code", "AUTHENTICATION_ERROR")
            reject_span.set_attribute("error.message", error_message)
            
            # Add correlation ID if available
            correlation_id = get_correlation_id(request)
            if correlation_id:
                reject_span.set_attribute("correlation.id", correlation_id)
            
            reject_span.set_status(Status(StatusCode.ERROR, error_message))
            reject_span.record_exception(exc)
    
    # Check if this is a JWT authentication failure (should return AUTH_FAILED)
    jwt_failure_messages = [
        "Authentication failed. Please log in again.",
        "Invalid or expired token",
        "Missing bearer token",
        "Invalid token type",
        "User ID not found in token",
        "Failed to verify token"
    ]
    
    is_jwt_failure = any(msg in error_message for msg in jwt_failure_messages)
    error_code = "AUTH_FAILED" if is_jwt_failure else "AUTHENTICATION_ERROR"
    
    # Log to OpenSearch
    _log_error_to_opensearch(request, 401, error_code, error_message)
    
    error_detail = ErrorDetail(
        message=error_message,
        code=error_code,
        timestamp=time.time()
    )
    # Use model_dump() for Pydantic v2 compatibility, fallback to dict() for v1
    # Exclude timestamp from response
    try:
        detail_dict = error_detail.model_dump(exclude={'timestamp'}) if hasattr(error_detail, 'model_dump') else error_detail.dict(exclude={'timestamp'})
    except Exception:
        detail_dict = error_detail.dict(exclude={'timestamp'})
    
    response_content = {"detail": detail_dict}
    logger.info(f"AuthenticationError handler returning structured response: {response_content}")
    
    return JSONResponse(
        status_code=401,
        content=response_content
    )


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler_wrapper(request: Request, exc: AuthenticationError):
        """Wrapper to call the authentication error handler."""
        logger.error(f"🔴 AuthenticationError handler wrapper CALLED for path: {request.url.path}, detail: {exc.detail}, message: {getattr(exc, 'message', None)}")
        try:
            response = await authentication_error_handler(request, exc)
            logger.error(f"🔴 AuthenticationError handler returning response: {response.body.decode() if hasattr(response, 'body') else 'no body'}")
            return response
        except Exception as e:
            logger.error(f"🔴 ERROR in authentication_error_handler: {e}", exc_info=True)
            raise
    
    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authorization")
                reject_span.set_attribute("auth.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("http.method", request.method)
                reject_span.set_attribute("http.path", request.url.path)
                reject_span.set_attribute("http.status_code", 403)
                reject_span.set_attribute("error.code", "AUTHORIZATION_ERROR")
                reject_span.set_attribute("error.message", exc.message)
                
                # Add correlation ID if available
                correlation_id = get_correlation_id(request)
                if correlation_id:
                    reject_span.set_attribute("correlation.id", correlation_id)
                
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                reject_span.record_exception(exc)
        
        # Log to OpenSearch
        _log_error_to_opensearch(request, 403, "AUTHORIZATION_ERROR", exc.message)
        
        error_detail = ErrorDetail(
            message=exc.message,
            code="AUTHORIZATION_ERROR",
            timestamp=time.time()
        )
        # Exclude timestamp from response
        try:
            detail_dict = error_detail.model_dump(exclude={'timestamp'}) if hasattr(error_detail, 'model_dump') else error_detail.dict(exclude={'timestamp'})
        except Exception:
            detail_dict = error_detail.dict(exclude={'timestamp'})
        return JSONResponse(
            status_code=403,
            content={"detail": detail_dict}
        )
    
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitExceededError):
        """Handle rate limit exceeded errors."""
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("rate_limit.operation", "reject_rate_limit")
                reject_span.set_attribute("rate_limit.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("http.method", request.method)
                reject_span.set_attribute("http.path", request.url.path)
                reject_span.set_attribute("http.status_code", 429)
                reject_span.set_attribute("error.code", "RATE_LIMIT_EXCEEDED")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("rate_limit.retry_after", exc.retry_after)
                
                # Add correlation ID if available
                correlation_id = get_correlation_id(request)
                if correlation_id:
                    reject_span.set_attribute("correlation.id", correlation_id)
                
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                reject_span.record_exception(exc)
        
        # Log to OpenSearch
        _log_error_to_opensearch(request, 429, "RATE_LIMIT_EXCEEDED", exc.message)
        
        error_detail = ErrorDetail(
            message=exc.message,
            code="RATE_LIMIT_EXCEEDED",
            timestamp=time.time()
        )
        # Exclude timestamp from response
        try:
            detail_dict = error_detail.model_dump(exclude={'timestamp'}) if hasattr(error_detail, 'model_dump') else error_detail.dict(exclude={'timestamp'})
        except Exception:
            detail_dict = error_detail.dict(exclude={'timestamp'})
        return JSONResponse(
            status_code=429,
            content={"detail": detail_dict},
            headers={"Retry-After": str(exc.retry_after)}
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle generic HTTP exceptions."""
        # CRITICAL: Check for AuthenticationError FIRST before any other processing
        # This ensures our custom handler is used instead of FastAPI's default
        if isinstance(exc, AuthenticationError):
            logger.error(f"🔴 HTTPException handler delegating AuthenticationError for path: {request.url.path}, detail: {exc.detail}")
            try:
                response = await authentication_error_handler(request, exc)
                logger.error(f"🔴 HTTPException handler got response from authentication_error_handler")
                return response
            except Exception as e:
                logger.error(f"🔴 ERROR in HTTPException handler delegation: {e}", exc_info=True)
                raise
        if isinstance(exc, AuthorizationError):
            return await authorization_error_handler(request, exc)
        
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
                    # Store only trace_id - OpenSearch will use URL template to construct full URL
                jaeger_trace_url = trace_id
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
        # Skip logging 400-series errors - these are logged at API Gateway level to avoid duplicates
        if LOGGING_AVAILABLE:
            if 400 <= exc.status_code < 500:
                # Don't log 400-series errors - gateway handles this
                pass
            else:
                logger.error(
                    f"{method} {path} - {exc.status_code} - 0.000s",
                    extra={"context": log_context}
                )
        else:
            if 400 <= exc.status_code < 500:
                # Don't log 400-series errors - gateway handles this
                pass
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
        
        # For string details (like AuthenticationError), always wrap in ErrorDetail format
        # This ensures consistent structured error responses
        error_detail = ErrorDetail(
            message=error_message,
            code=error_code,
            timestamp=time.time()
        )
        # Use model_dump() for Pydantic v2 compatibility, exclude timestamp
        try:
            detail_dict = error_detail.model_dump(exclude={'timestamp'}) if hasattr(error_detail, 'model_dump') else error_detail.dict(exclude={'timestamp'})
        except Exception:
            detail_dict = error_detail.dict(exclude={'timestamp'})
        
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail_dict}
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
                    # Store only trace_id - OpenSearch will use URL template to construct full URL
                jaeger_trace_url = trace_id
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
        # Exclude timestamp from response
        try:
            detail_dict = error_detail.model_dump(exclude={'timestamp'}) if hasattr(error_detail, 'model_dump') else error_detail.dict(exclude={'timestamp'})
        except Exception:
            detail_dict = error_detail.dict(exclude={'timestamp'})
        return JSONResponse(
            status_code=500,
            content={"detail": detail_dict}
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors."""
        method = request.method
        path = request.url.path
        correlation_id = get_correlation_id(request)
        
        # Create span for validation error if tracer is available
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("validation.operation", "reject_validation")
                reject_span.set_attribute("validation.rejected", True)
                reject_span.set_attribute("http.method", method)
                reject_span.set_attribute("http.path", path)
                reject_span.set_attribute("http.status_code", 422)
                reject_span.set_attribute("error.code", "VALIDATION_ERROR")
                reject_span.set_attribute("validation.error_count", len(exc.errors()))
                
                # Add correlation ID if available
                if correlation_id:
                    reject_span.set_attribute("correlation.id", correlation_id)
                
                # Decision point: Analyze validation errors
                with tracer.start_as_current_span("validation.decision.analyze_errors") as analyze_span:
                    analyze_span.set_attribute("validation.decision", "analyze_validation_errors")
                    analyze_span.set_attribute("validation.error_count", len(exc.errors()))
                    
                    # Add individual error details to span
                    for idx, error in enumerate(exc.errors()[:5]):  # Limit to first 5 errors
                        field_path = ".".join(str(loc) for loc in error.get("loc", []))
                        analyze_span.set_attribute(f"validation.error.{idx}.field", field_path)
                        analyze_span.set_attribute(f"validation.error.{idx}.type", error.get("type", "unknown"))
                        analyze_span.set_attribute(f"validation.error.{idx}.message", error.get("msg", ""))
                    
                    analyze_span.set_status(Status(StatusCode.OK))
                
                reject_span.set_status(Status(StatusCode.ERROR, "Validation failed"))
                reject_span.record_exception(exc)
        
        # Log to OpenSearch (validation errors happen during body parsing, before route handler)
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Extract trace_id from OpenTelemetry context for Jaeger URL
        trace_id = None
        jaeger_trace_url = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    span_context = current_span.get_span_context()
                    trace_id = format(span_context.trace_id, '032x')
                    # Store only trace_id - OpenSearch will use URL template to construct full URL
                jaeger_trace_url = trace_id
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

