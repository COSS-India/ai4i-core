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
    ErrorDetail,
    ServiceError,
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    AudioProcessingError
)
from services.constants.error_messages import (
    AUTH_FAILED,
    AUTH_FAILED_TTS_MESSAGE,
    RATE_LIMIT_EXCEEDED,
    RATE_LIMIT_EXCEEDED_TTS_MESSAGE,
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_TTS_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_TTS_MESSAGE,
    INTERNAL_SERVER_ERROR,
    INTERNAL_SERVER_ERROR_MESSAGE,
    NO_TEXT_INPUT,
    NO_TEXT_INPUT_MESSAGE,
    TEXT_TOO_LONG,
    TEXT_TOO_LONG_MESSAGE
)
import logging
import time
import traceback
from ai4icore_logging import get_logger, get_correlation_id, get_organization

# Import OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

logger = get_logger(__name__)
tracer = trace.get_tracer("tts-service") if TRACING_AVAILABLE else None


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors and convert to custom error format."""
        errors = exc.errors()
        
        # Check for specific validation errors and map them to our error codes
        for error in errors:
            error_loc = error.get("loc", [])
            error_msg = str(error.get("msg", "")).lower()
            error_type = error.get("type", "")
            
            # Convert location tuple to list of strings for easier checking
            loc_list = [str(loc) for loc in error_loc]
            
            # Check if it's a source field error
            if "source" in loc_list:
                # Check for text too long error (various message formats)
                if "5000" in error_msg or "exceed" in error_msg or "cannot exceed" in error_msg:
                    error_detail = ErrorDetail(
                        code=TEXT_TOO_LONG,
                        message=TEXT_TOO_LONG_MESSAGE
                    )
                    return JSONResponse(
                        status_code=400,
                        content={"detail": error_detail.dict()}
                    )
                # Check for empty source
                elif "empty" in error_msg or "required" in error_msg or "cannot be empty" in error_msg:
                    error_detail = ErrorDetail(
                        code=NO_TEXT_INPUT,
                        message=NO_TEXT_INPUT_MESSAGE
                    )
                    return JSONResponse(
                        status_code=400,
                        content={"detail": error_detail.dict()}
                    )
        
        # For other validation errors, return generic invalid request
        error_detail = ErrorDetail(
            code=INVALID_REQUEST,
            message=INVALID_REQUEST_TTS_MESSAGE
        )
        return JSONResponse(
            status_code=422,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get correlation ID if available
        correlation_id = get_correlation_id(request)
        
        # Determine specific error code based on exception type and message
        # Match the exact error codes used by API Gateway for consistency
        from middleware.exceptions import InvalidAPIKeyError, ExpiredAPIKeyError
        if isinstance(exc, InvalidAPIKeyError):
            error_code = "INVALID_API_KEY"
            error_reason = "invalid_api_key"
        elif isinstance(exc, ExpiredAPIKeyError):
            error_code = "EXPIRED_API_KEY"
            error_reason = "expired_api_key"
        elif "Invalid or expired token" in exc.message or "token" in exc.message.lower() or "expired" in exc.message.lower():
            # Map token-related errors to AUTHENTICATION_REQUIRED (matching API Gateway format)
            error_code = "AUTHENTICATION_REQUIRED"
            error_reason = "authentication_failed"
        else:
            error_code = "AUTHENTICATION_ERROR"
            error_reason = "authentication_failed"
        
        # Create span for authentication error if tracer is available
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authentication")
                reject_span.set_attribute("auth.rejected", True)
                reject_span.set_attribute("error.type", type(exc).__name__)
                reject_span.set_attribute("error.reason", error_reason)
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", error_code)
                reject_span.set_attribute("http.status_code", 401)
                reject_span.set_attribute("http.method", method)
                reject_span.set_attribute("http.route", path)
                if correlation_id:
                    reject_span.set_attribute("correlation.id", correlation_id)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
        
        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Get organization from request.state or context
        organization = getattr(request.state, "organization", None)
        if not organization:
            try:
                organization = get_organization()
            except Exception:
                pass
        
        # Calculate processing time (approximate, since we don't have start_time)
        processing_time = 0.001  # Minimal time for auth errors
        
        # Build context matching RequestLoggingMiddleware format EXACTLY
        # This ensures 401 errors appear in OpenSearch with the same structure as 200
        log_context = {
            "method": method,
            "path": path,
            "status_code": 401,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_code": error_code,
            "error_message": exc.message,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        if organization:
            log_context["organization"] = organization
        
        # Log with WARNING level to match RequestLoggingMiddleware for 4xx errors
        # Format: "{method} {path} - {status_code} - {duration}s" (same as RequestLoggingMiddleware)
        # This ensures 401 errors appear in OpenSearch with the same structure as 200
        # IMPORTANT: This explicit logging ensures errors are logged even if RequestLoggingMiddleware
        # doesn't catch the response (which can happen with exception handlers)
        # This matches exactly how NMT and OCR log authentication errors
        logger.warning(
            f"{method} {path} - 401 - {processing_time:.3f}s",
            extra={"context": log_context}
        )
        
        # Return error response matching the format seen in API Gateway
        # Format: {"detail": {"error": "ERROR_CODE", "message": "..."}}
        return JSONResponse(
            status_code=401,
            content={"detail": {"error": error_code, "message": exc.message}}
        )
    
    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get correlation ID if available
        correlation_id = get_correlation_id(request)
        
        # Create span for authorization error if tracer is available
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authorization")
                reject_span.set_attribute("auth.rejected", True)
                reject_span.set_attribute("error.type", "AuthorizationError")
                reject_span.set_attribute("error.reason", "authorization_failed")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", "AUTHORIZATION_ERROR")
                reject_span.set_attribute("http.status_code", 403)
                reject_span.set_attribute("http.method", method)
                reject_span.set_attribute("http.route", path)
                if correlation_id:
                    reject_span.set_attribute("correlation.id", correlation_id)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
        
        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Get organization from request.state or context
        organization = getattr(request.state, "organization", None)
        if not organization:
            try:
                organization = get_organization()
            except Exception:
                pass
        
        # Calculate processing time (approximate)
        processing_time = 0.001
        
        # Build context matching RequestLoggingMiddleware format
        log_context = {
            "method": method,
            "path": path,
            "status_code": 403,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_code": "AUTHORIZATION_ERROR",
            "error_message": exc.message,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        if organization:
            log_context["organization"] = organization
        
        # Log with WARNING level
        # IMPORTANT: This explicit logging ensures errors are logged even if RequestLoggingMiddleware
        # doesn't catch the response (which can happen with exception handlers)
        logger.warning(
            f"{method} {path} - 403 - {processing_time:.3f}s",
            extra={"context": log_context}
        )
        
        # Return error response matching the format seen in API Gateway
        # Format: {"detail": {"error": "ERROR_CODE", "message": "..."}}
        return JSONResponse(
            status_code=403,
            content={"detail": {"error": "AUTHORIZATION_ERROR", "message": exc.message}}
        )
    
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitExceededError):
        """Handle rate limit exceeded errors."""
        error_detail = ErrorDetail(
            message=RATE_LIMIT_EXCEEDED_TTS_MESSAGE.format(x=exc.retry_after),
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
        # Extract context for logging
        correlation_id = get_correlation_id(request)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        service_id = getattr(request.state, "service_id", None)
        
        # Record error in Jaeger span
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.code", "HTTP_ERROR")
                    current_span.set_attribute("error.message", str(exc.detail))
                    current_span.set_attribute("http.status_code", exc.status_code)
                    if service_id:
                        current_span.set_attribute("tts.service_id", service_id)
                    if correlation_id:
                        current_span.set_attribute("correlation.id", correlation_id)
                    current_span.set_status(Status(StatusCode.ERROR, str(exc.detail)))
            except Exception:
                pass
        
        # Log 500 errors with full context
        if exc.status_code == 500:
            logger.error(
                f"HTTP 500 error in TTS service: {exc.detail}",
                extra={
                    "context": {
                        "error_type": "HTTPException",
                        "error_message": str(exc.detail),
                        "status_code": 500,
                        "service_id": service_id,
                        "user_id": user_id,
                        "api_key_id": api_key_id,
                        "correlation_id": correlation_id,
                        "path": request.url.path,
                        "method": request.method,
                    }
                },
                exc_info=True
            )
        
        # Check if detail is already an ErrorDetail dict
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        
        # Map specific status codes to error constants
        if exc.status_code == 503:
            error_detail = ErrorDetail(
                message=SERVICE_UNAVAILABLE_TTS_MESSAGE,
                code=SERVICE_UNAVAILABLE
            )
        elif exc.status_code == 400:
            error_detail = ErrorDetail(
                message=INVALID_REQUEST_TTS_MESSAGE,
                code=INVALID_REQUEST
            )
        elif exc.status_code == 401:
            error_detail = ErrorDetail(
                message=AUTH_FAILED_TTS_MESSAGE,
                code=AUTH_FAILED
            )
        elif exc.status_code == 500:
            # For 500 errors, use the actual error message
            error_detail = ErrorDetail(
                message=str(exc.detail) if exc.detail else INTERNAL_SERVER_ERROR_MESSAGE,
                code=INTERNAL_SERVER_ERROR
            )
        else:
            error_detail = ErrorDetail(
                message=str(exc.detail),
                code="HTTP_ERROR"
            )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_detail.dict()}
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        # Extract context for logging
        correlation_id = get_correlation_id(request)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        service_id = getattr(request.state, "service_id", None)
        triton_endpoint = getattr(request.state, "triton_endpoint", None)
        model_name = getattr(request.state, "triton_model_name", None)
        
        # Record error in Jaeger span
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.code", "INTERNAL_ERROR")
                    current_span.set_attribute("error.message", str(exc))
                    current_span.set_attribute("error.type", type(exc).__name__)
                    current_span.set_attribute("http.status_code", 500)
                    if service_id:
                        current_span.set_attribute("tts.service_id", service_id)
                    if triton_endpoint:
                        current_span.set_attribute("triton.endpoint", triton_endpoint)
                    if model_name:
                        current_span.set_attribute("triton.model_name", model_name)
                    if correlation_id:
                        current_span.set_attribute("correlation.id", correlation_id)
                    current_span.record_exception(exc)
                    current_span.set_status(Status(StatusCode.ERROR, str(exc)))
            except Exception:
                pass
        
        # Log the full error with traceback and context
        logger.error(
            f"Unexpected error in TTS service: {exc}",
            extra={
                "context": {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "status_code": 500,
                    "service_id": service_id,
                    "triton_endpoint": triton_endpoint,
                    "model_name": model_name,
                    "user_id": user_id,
                    "api_key_id": api_key_id,
                    "correlation_id": correlation_id,
                    "path": request.url.path,
                    "method": request.method,
                }
            },
            exc_info=True
        )
        
        error_detail = ErrorDetail(
            message=str(exc) if str(exc) else INTERNAL_SERVER_ERROR_MESSAGE,
            code=INTERNAL_SERVER_ERROR
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
