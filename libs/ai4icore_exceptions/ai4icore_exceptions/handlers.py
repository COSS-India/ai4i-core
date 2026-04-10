"""
Global exception handlers for ALL microservices.

Register once at app startup -- consistent error responses across the platform.

Usage:
    from ai4icore_exceptions import register_exception_handlers
    register_exception_handlers(app)
"""

import logging
import re
import time
import traceback

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .exceptions import (
    AppError,
    AuthenticationError,
    AuthenticationRequiredError,
    AuthorizationError,
    ErrorDetail,
    PipelineError,
    RateLimitExceededError,
    ServiceError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
    ValidationError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Telemetry helpers (optional -- works without OpenTelemetry installed)
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False

AUTH_FAILED_MESSAGE = "Authentication failed. Please log in again."


def _strip_status_prefix(message: str) -> str:
    """Remove leading HTTP status codes like ``403: `` from error messages."""
    if not isinstance(message, str):
        return str(message)
    m = re.match(r"^\s*(\d{3})\s*:\s*(.+)$", message)
    return m.group(2) if m else message


def _error_detail_response(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Return the standard ``{"detail": {...}}`` envelope used by all inference services."""
    body = {
        "detail": ErrorDetail(
            message=message,
            code=code,
            timestamp=time.time(),
        ).dict()
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def _trace_rejection(
    span_name: str,
    *,
    error_type: str,
    error_code: str,
    error_message: str,
    http_status: int,
    extra_attrs: dict | None = None,
) -> None:
    """Create an OTel rejection span if telemetry is available."""
    if not _OTEL_AVAILABLE:
        return
    tracer = trace.get_tracer("ai4icore_exceptions")
    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("error.type", error_type)
        span.set_attribute("error.code", error_code)
        span.set_attribute("error.message", error_message)
        span.set_attribute("http.status_code", http_status)
        for k, v in (extra_attrs or {}).items():
            span.set_attribute(k, v)
        span.set_status(Status(StatusCode.ERROR, error_message))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_exception_handlers(app: FastAPI) -> None:
    """
    Register standardised exception handlers on any FastAPI app.

    Call once during app creation.  All services get identical error shapes.
    Handles the full AppError hierarchy, FastAPI validation errors,
    HTTPException pass-through, and unhandled exceptions.
    """

    # ------------------------------------------------------------------
    # Authentication (401)
    # ------------------------------------------------------------------
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        raw_msg = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        error_msg = _strip_status_prefix(raw_msg)

        _trace_rejection(
            "request.reject",
            error_type="AuthenticationError",
            error_code="AUTHENTICATION_ERROR",
            error_message=error_msg,
            http_status=401,
            extra_attrs={"auth.operation": "reject_authentication", "auth.rejected": True},
        )

        # API key ownership mismatch
        if "API key does not belong to the authenticated user" in (error_msg or ""):
            return _error_detail_response(
                401, "AUTHORIZATION_ERROR",
                "API key does not belong to the authenticated user",
            )

        # Invalid API key -- check if header was actually provided
        if "Invalid API key" in (error_msg or ""):
            if not request.headers.get("x-api-key"):
                return _error_detail_response(
                    401, "API_KEY_MISSING",
                    "API key is required to access this service.",
                )
            return _error_detail_response(
                401, "AUTHORIZATION_ERROR",
                _strip_status_prefix(error_msg or "Invalid API key"),
            )

        # Missing API key
        if "Missing API key" in (error_msg or ""):
            return _error_detail_response(
                401, "API_KEY_MISSING",
                "API key is required to access this service.",
            )

        # Default: token expired / invalid / generic auth failure
        return _error_detail_response(401, "AUTHENTICATION_ERROR", AUTH_FAILED_MESSAGE)

    # ------------------------------------------------------------------
    # Authorization (403)
    # ------------------------------------------------------------------
    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        _request: Request, exc: AuthorizationError
    ) -> JSONResponse:
        message = _strip_status_prefix(exc.message)

        _trace_rejection(
            "request.reject",
            error_type="AuthorizationError",
            error_code="AUTHORIZATION_ERROR",
            error_message=message,
            http_status=403,
            extra_attrs={"auth.operation": "reject_authorization", "auth.rejected": True},
        )

        # Keep detailed permission / ownership messages as-is
        if not (
            "permission" in message.lower()
            or "does not have" in message.lower()
            or "api key does not belong" in message.lower()
        ):
            if not message.startswith("Authorization error"):
                message = f"Authorization error: {message}"

        return _error_detail_response(403, "AUTHORIZATION_ERROR", message)

    # ------------------------------------------------------------------
    # Rate limiting (429)
    # ------------------------------------------------------------------
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_error_handler(
        _request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        _trace_rejection(
            "request.reject",
            error_type="RateLimitExceededError",
            error_code="RATE_LIMIT_EXCEEDED",
            error_message=exc.message,
            http_status=429,
            extra_attrs={"rate_limit.retry_after": exc.retry_after},
        )
        return _error_detail_response(
            429, "RATE_LIMIT_EXCEEDED", exc.message,
            headers={"Retry-After": str(exc.retry_after)},
        )

    # ------------------------------------------------------------------
    # App-level validation errors (custom ValidationError)
    # ------------------------------------------------------------------
    @app.exception_handler(ValidationError)
    async def validation_app_error(
        _request: Request, exc: ValidationError
    ) -> JSONResponse:
        details = {"errors": exc.errors} if exc.errors else None
        body: dict = {
            "detail": {
                "code": exc.code,
                "message": exc.message,
                "timestamp": time.time(),
            }
        }
        if details:
            body["detail"]["details"] = details
        return JSONResponse(status_code=exc.status_code, content=body)

    # ------------------------------------------------------------------
    # Service / infrastructure errors (TritonInferenceError, etc.)
    # ------------------------------------------------------------------
    @app.exception_handler(ServiceError)
    async def service_error_handler(
        _request: Request, exc: ServiceError
    ) -> JSONResponse:
        body: dict = {
            "detail": {
                "code": exc.code,
                "message": exc.message,
                "timestamp": time.time(),
            }
        }
        if exc.service_error:
            body["detail"]["details"] = exc.service_error
        return JSONResponse(status_code=exc.status_code, content=body)

    # ------------------------------------------------------------------
    # Pipeline errors
    # ------------------------------------------------------------------
    @app.exception_handler(PipelineError)
    async def pipeline_error_handler(
        _request: Request, exc: PipelineError
    ) -> JSONResponse:
        details: dict = {}
        if exc.task_index is not None:
            details["task_index"] = exc.task_index
        if exc.task_type:
            details["task_type"] = exc.task_type
        if exc.service_error:
            details["service_error"] = exc.service_error
        body: dict = {
            "detail": {
                "code": exc.code,
                "message": exc.message,
                "timestamp": time.time(),
            }
        }
        if details:
            body["detail"]["details"] = details
        return JSONResponse(status_code=exc.status_code, content=body)

    # ------------------------------------------------------------------
    # Generic AppError catch-all
    # ------------------------------------------------------------------
    @app.exception_handler(AppError)
    async def app_error_handler(
        _request: Request, exc: AppError
    ) -> JSONResponse:
        return _error_detail_response(exc.status_code, exc.code, exc.message)

    # ------------------------------------------------------------------
    # Pydantic / FastAPI request validation (422)
    # ------------------------------------------------------------------
    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()

        _trace_rejection(
            "request.reject",
            error_type="RequestValidationError",
            error_code="VALIDATION_ERROR",
            error_message=f"Validation failed with {len(errors)} error(s)",
            http_status=422,
            extra_attrs={"validation.error_count": len(errors)},
        )

        logger.warning(
            "%s %s - 422 validation error (%d errors)",
            request.method, request.url.path, len(errors),
        )

        # Return raw Pydantic errors (consistent with existing service behavior)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": errors},
        )

    # ------------------------------------------------------------------
    # Generic HTTPException (pass-through from FastAPI / upstream)
    # ------------------------------------------------------------------
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        # If it's actually an AppError subclass, delegate to the right handler
        if isinstance(exc, AuthenticationError):
            return await authentication_error_handler(request, exc)
        if isinstance(exc, AuthorizationError):
            return await authorization_error_handler(request, exc)

        detail_val = getattr(exc, "detail", None)

        # Preserve structured detail from upstream (API Gateway / ErrorDetail)
        if isinstance(detail_val, dict):
            if "error" in detail_val and "message" in detail_val:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": {"error": detail_val["error"], "message": detail_val["message"]}},
                )
            if "code" in detail_val and "message" in detail_val:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": {"code": detail_val["code"], "message": detail_val["message"]}},
                )

        # Pydantic model as detail
        if hasattr(detail_val, "dict"):
            try:
                return JSONResponse(status_code=exc.status_code, content={"detail": detail_val.dict()})
            except Exception:
                pass

        error_code = getattr(exc, "error_code", None) or getattr(exc, "code", None) or "HTTP_ERROR"
        error_message = getattr(exc, "message", None) or (str(detail_val) if detail_val is not None else str(exc))

        return _error_detail_response(exc.status_code, error_code, error_message)

    # ------------------------------------------------------------------
    # Unhandled / catch-all (500)
    # ------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        # Unwrap ExceptionGroup (Python 3.11+)
        actual_exc = exc
        try:
            if hasattr(exc, "exceptions") and exc.exceptions:
                actual_exc = exc.exceptions[0]
        except (AttributeError, IndexError):
            pass

        # Delegate wrapped exceptions to their specific handlers
        if isinstance(actual_exc, RateLimitExceededError):
            return await rate_limit_error_handler(request, actual_exc)
        if isinstance(actual_exc, AuthenticationError):
            return await authentication_error_handler(request, actual_exc)
        if isinstance(actual_exc, AuthorizationError):
            return await authorization_error_handler(request, actual_exc)
        if isinstance(actual_exc, HTTPException):
            return await http_exception_handler(request, actual_exc)

        # Record in OTel if available
        if _OTEL_AVAILABLE:
            try:
                span = trace.get_current_span()
                if span and span.is_recording():
                    span.set_attribute("error.type", type(actual_exc).__name__)
                    span.set_attribute("error.message", str(actual_exc))
                    span.record_exception(actual_exc)
                    span.set_status(Status(StatusCode.ERROR, str(actual_exc)))
            except Exception:
                pass

        logger.error("Unhandled exception: %s", actual_exc)
        logger.error("Traceback: %s", traceback.format_exc())

        return _error_detail_response(500, "INTERNAL_ERROR", "Internal server error")
