"""
Global error handler middleware for consistent error responses.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id, get_logger

from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError, 
    RateLimitExceededError,
    ErrorDetail,
    ServiceError,
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    TextProcessingError
)
from services.constants.error_messages import (
    AUTH_FAILED,
    AUTH_FAILED_NMT_MESSAGE,
    RATE_LIMIT_EXCEEDED,
    RATE_LIMIT_EXCEEDED_NMT_MESSAGE,
    SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE_NMT_MESSAGE,
    INVALID_REQUEST,
    INVALID_REQUEST_NMT_MESSAGE,
    INTERNAL_SERVER_ERROR,
    INTERNAL_SERVER_ERROR_MESSAGE,
    NO_TEXT_INPUT,
    NO_TEXT_INPUT_NMT_MESSAGE,
    TEXT_TOO_SHORT,
    TEXT_TOO_SHORT_NMT_MESSAGE,
    TEXT_TOO_LONG,
    TEXT_TOO_LONG_NMT_MESSAGE,
    INVALID_CHARACTERS,
    INVALID_CHARACTERS_NMT_MESSAGE,
    EMPTY_INPUT,
    EMPTY_INPUT_NMT_MESSAGE,
    SAME_LANGUAGE_ERROR,
    SAME_LANGUAGE_ERROR_MESSAGE,
    LANGUAGE_PAIR_NOT_SUPPORTED,
    LANGUAGE_PAIR_NOT_SUPPORTED_MESSAGE,
    TRANSLATION_FAILED,
    TRANSLATION_FAILED_MESSAGE
)
import logging
import traceback

logger = get_logger(__name__)
tracer = trace.get_tracer("nmt-service")


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authentication")
                reject_span.set_attribute("auth.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "AuthenticationError")
                reject_span.set_attribute("error.reason", "authentication_failed")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", "AUTHENTICATION_ERROR")
                reject_span.set_attribute("http.status_code", 401)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically in parent spans when exception was raised
        
        error_detail = ErrorDetail(
            message=AUTH_FAILED_NMT_MESSAGE,
            code=AUTH_FAILED
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
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "AuthorizationError")
                reject_span.set_attribute("error.reason", "authorization_failed")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", "AUTHORIZATION_ERROR")
                reject_span.set_attribute("http.status_code", 403)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically in parent spans when exception was raised
        
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
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("rate_limit.operation", "reject_rate_limit")
                reject_span.set_attribute("rate_limit.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "RateLimitExceededError")
                reject_span.set_attribute("error.reason", "rate_limit_exceeded")
                reject_span.set_attribute("error.message", exc.message)
                reject_span.set_attribute("error.code", "RATE_LIMIT_EXCEEDED")
                reject_span.set_attribute("rate_limit.retry_after", exc.retry_after)
                reject_span.set_attribute("http.status_code", 429)
                reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically in parent spans when exception was raised
        
        error_detail = ErrorDetail(
            message=RATE_LIMIT_EXCEEDED_NMT_MESSAGE.format(x=exc.retry_after),
            code=RATE_LIMIT_EXCEEDED
        )
        return JSONResponse(
            status_code=429,
            content={"detail": error_detail.dict()},
            headers={"Retry-After": str(exc.retry_after)}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle request validation errors (422 Unprocessable Entity)."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get correlation ID if available
        correlation_id = get_correlation_id(request)
        
        # Build error messages
        error_messages = []
        for error in exc.errors():
            loc = ".".join(map(str, error["loc"]))
            error_messages.append(f"{loc}: {error['msg']}")
        
        full_message = f"Validation error: {'; '.join(error_messages)}"
        
        # Create span for validation error if tracer is available
        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("validation.operation", "reject_validation")
                reject_span.set_attribute("validation.rejected", True)
                reject_span.set_attribute("http.method", method)
                reject_span.set_attribute("http.route", path)
                reject_span.set_attribute("http.status_code", 422)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "RequestValidationError")
                reject_span.set_attribute("error.reason", "validation_failed")
                reject_span.set_attribute("error.message", full_message)
                reject_span.set_attribute("error.code", "VALIDATION_ERROR")
                reject_span.set_attribute("validation.error_count", len(exc.errors()))
                
                if correlation_id:
                    reject_span.set_attribute("correlation.id", correlation_id)
                
                # Decision point: Analyze validation errors
                with tracer.start_as_current_span("validation.decision.analyze_errors") as analyze_span:
                    analyze_span.set_attribute("validation.decision", "analyze_validation_errors")
                    analyze_span.set_attribute("validation.error_count", len(exc.errors()))
                    
                    # Categorize errors
                    missing_fields = []
                    invalid_types = []
                    invalid_values = []
                    
                    for idx, error in enumerate(exc.errors()):
                        loc = ".".join(map(str, error["loc"]))
                        error_type = error.get("type", "")
                        error_msg = error.get("msg", "")
                        
                        reject_span.set_attribute(f"validation.error.{idx}.location", loc)
                        reject_span.set_attribute(f"validation.error.{idx}.message", error_msg)
                        reject_span.set_attribute(f"validation.error.{idx}.type", error_type)
                        
                        # Categorize
                        if "missing" in error_type.lower() or "required" in error_msg.lower():
                            missing_fields.append(loc)
                        elif "type" in error_type.lower() or "value_error" in error_type.lower():
                            invalid_types.append(loc)
                        else:
                            invalid_values.append(loc)
                    
                    if missing_fields:
                        analyze_span.set_attribute("validation.missing_fields", ",".join(missing_fields))
                        reject_span.set_attribute("validation.missing_fields", ",".join(missing_fields))
                    if invalid_types:
                        analyze_span.set_attribute("validation.invalid_types", ",".join(invalid_types))
                        reject_span.set_attribute("validation.invalid_types", ",".join(invalid_types))
                    if invalid_values:
                        analyze_span.set_attribute("validation.invalid_values", ",".join(invalid_values))
                        reject_span.set_attribute("validation.invalid_values", ",".join(invalid_values))
                    
                    analyze_span.set_attribute("validation.decision.result", "rejected")
                    analyze_span.set_status(Status(StatusCode.ERROR, full_message))
                
                reject_span.add_event("validation.failed", {
                    "error_count": len(exc.errors()),
                    "message": full_message
                })
                reject_span.set_status(Status(StatusCode.ERROR, full_message))
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically when RequestValidationError was raised
        
        # Log the validation error with the SAME format as RequestLoggingMiddleware
        # This ensures 422 errors appear in OpenSearch with consistent format
        # 
        # WHY THIS IS NEEDED:
        # - FastAPI raises RequestValidationError DURING body parsing (before route handler)
        # - Exception handler returns 422 response
        # - Response SHOULD go through RequestLoggingMiddleware, but sometimes doesn't
        # - This explicit logging ensures 422 errors are ALWAYS logged to OpenSearch
        # - This is STANDARD PRACTICE: All HTTP responses (200, 401, 403, 422, 500) should be logged
        #
        # Extract auth context from request.state if available (same as RequestLoggingMiddleware)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Calculate processing time (approximate, since we don't have start_time)
        # Validation errors happen very quickly (during body parsing)
        processing_time = 0.001  # Minimal time for validation errors
        
        # Build context matching RequestLoggingMiddleware format EXACTLY
        # This ensures 422 errors appear in OpenSearch with the same structure as 401/403/200
        log_context = {
            "method": method,
            "path": path,
            "status_code": 422,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            # Additional validation-specific fields for better debugging
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
        
        # Don't log 422 errors here - they are logged at API Gateway level to avoid duplicates
        # The response will be logged by the gateway when it receives the 422 status code
        
        error_detail = ErrorDetail(
            message="Validation error",
            code="VALIDATION_ERROR",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )
    
    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        """Handle service-specific errors with Jaeger tracing."""
        # Record error in Jaeger span
        if tracer:
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
        # Record error in Jaeger span
        if tracer:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.code", "HTTP_ERROR")
                    current_span.set_attribute("error.message", str(exc.detail))
                    current_span.set_attribute("http.status_code", exc.status_code)
                    current_span.set_status(Status(StatusCode.ERROR, str(exc.detail)))
            except Exception:
                pass
        
        # Check if detail is already an ErrorDetail dict
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        
        # Map specific status codes to error constants
        if exc.status_code == 503:
            error_detail = ErrorDetail(
                message=SERVICE_UNAVAILABLE_NMT_MESSAGE,
                code=SERVICE_UNAVAILABLE
            )
        elif exc.status_code == 400:
            error_detail = ErrorDetail(
                message=INVALID_REQUEST_NMT_MESSAGE,
                code=INVALID_REQUEST
            )
        elif exc.status_code == 401:
            error_detail = ErrorDetail(
                message=AUTH_FAILED_NMT_MESSAGE,
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
        
        logger.error(f"Unexpected error: {exc}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        error_detail = ErrorDetail(
            message=str(exc) if str(exc) else INTERNAL_SERVER_ERROR_MESSAGE,
            code=INTERNAL_SERVER_ERROR
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
