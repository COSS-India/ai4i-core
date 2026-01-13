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
        error_detail = ErrorDetail(
            message=AUTH_FAILED_TTS_MESSAGE,
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
        # Record error in Jaeger span
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
        logger.error(f"Unexpected error: {exc}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
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
                    current_span.record_exception(exc)
                    current_span.set_status(Status(StatusCode.ERROR, str(exc)))
            except Exception:
                pass
        
        error_detail = ErrorDetail(
            message=str(exc) if str(exc) else INTERNAL_SERVER_ERROR_MESSAGE,
            code=INTERNAL_SERVER_ERROR
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
