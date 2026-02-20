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
)
import logging
import time
import traceback
import re

# NOTE:
# Unlike ASR/API Gateway containers, OCR's Docker image only copies this
# service directory into /app, so the shared `services.constants` package
# is not available at runtime. To keep the same user-facing message for
# expired/invalid tokens, we duplicate the constant value here.
AUTH_FAILED_MESSAGE = "Authentication failed. Please log in again."


def _strip_status_prefix(message: str) -> str:
    """
    Remove leading HTTP status codes like '403: ' from error messages so that
    user-facing messages match API Gateway (which does not include status
    codes in the message text).
    """
    if not isinstance(message, str):
        return message
    # Match patterns like "403: something" or "401 : something"
    m = re.match(r"^\s*(\d{3})\s*:\s*(.+)$", message)
    if m:
        return m.group(2)
    return message

logger = get_logger(__name__)
tracer = trace.get_tracer("ocr-service")


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors.

        For expired/invalid tokens we want to mirror API Gateway behavior and return
        the same user-facing message (`AUTH_FAILED_MESSAGE`), while still keeping
        the more specific details in tracing/logging.
        """
        # Capture original message for tracing and ownership checks
        error_msg = (
            getattr(exc, "message", None)
            or (str(exc.detail) if hasattr(exc, "detail") and exc.detail else "")
        )

        if tracer:
            with tracer.start_as_current_span("request.reject") as reject_span:
                reject_span.set_attribute("auth.operation", "reject_authentication")
                reject_span.set_attribute("auth.rejected", True)
                # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                reject_span.set_attribute("error.type", "AuthenticationError")
                reject_span.set_attribute("error.reason", "authentication_failed")
                # Record the low-level message for debugging
                reject_span.set_attribute("error.message", error_msg or exc.message)
                reject_span.set_attribute("error.code", "AUTHENTICATION_ERROR")
                reject_span.set_attribute("http.status_code", 401)
                reject_span.set_status(
                    Status(StatusCode.ERROR, error_msg or exc.message or AUTH_FAILED_MESSAGE)
                )
                # Don't record exception here - OpenTelemetry already recorded it
                # automatically in parent spans when exception was raised

        # For the ownership case, return explicit error + message fields with AUTHORIZATION_ERROR
        if "API key does not belong to the authenticated user" in (error_msg or ""):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "error": "AUTHORIZATION_ERROR",
                        "message": "API key does not belong to the authenticated user",
                    }
                },
            )

        # For invalid API key errors (BOTH mode with bad/missing key), mirror API
        # Gateway behavior by surfacing AUTHORIZATION_ERROR with the original message
        if "Invalid API key" in (error_msg or ""):
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

        # For missing API key, mirror API Gateway "API_KEY_MISSING" behavior
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
        # align user-facing message with API Gateway:
        #   "Authentication failed. Please log in again."
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
        
        # Preserve detailed API key permission messages from auth-service (e.g.,
        # "Invalid API key: This key does not have access to OCR service") so they
        # are not prefixed with "Authorization error: Insufficient permission."
        # Also strip any leading HTTP status codes like "403: " from the message.
        message = _strip_status_prefix(exc.message)
        if not (
            "permission" in message.lower()
            or "does not have" in message.lower()
            or "ocr.inference" in message
            or "OCR service" in message
        ):
            # For non-permission-related authorization errors, keep a clear prefix
            if not message.startswith("Authorization error"):
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
            message=exc.message,
            code="RATE_LIMIT_EXCEEDED",
            timestamp=time.time()
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
        import time
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
        
        # Log with WARNING level to match RequestLoggingMiddleware for 4xx errors
        # Format: "{method} {path} - {status_code} - {duration}s" (same as RequestLoggingMiddleware)
        # This ensures 422 errors appear in OpenSearch with the same format as 401/403
        # 
        # IMPORTANT: This MUST log because FastAPI's RequestValidationError happens
        # during body parsing, BEFORE the route handler, and the response from this
        # exception handler might not go through RequestLoggingMiddleware properly.
        try:
            logger.warning(
                f"{method} {path} - 422 - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        except Exception as log_exc:
            # Fallback: If structured logging fails, use basic logging
            logging.warning(
                f"422 Validation Error: {method} {path} - {full_message}",
                exc_info=log_exc
            )
        
        error_detail = ErrorDetail(
            message="Validation error",
            code="VALIDATION_ERROR",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle generic HTTP exceptions."""
        # Handle AuthenticationError here if it wasn't caught by the specific handler
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
            message="Internal server error",
            code="INTERNAL_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
