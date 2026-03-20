"""
Global exception handlers for ALL microservices.

Register once at app startup — consistent error responses across the platform.
All exceptions produce: {"success": false, "error": {"code": ..., "message": ..., "details": ...}}

Usage:
    from ai4icore_exceptions import register_exception_handlers
    register_exception_handlers(app)
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .exceptions import (
    AppError,
    ValidationError,
    ServiceError,
    PipelineError,
)

logger = logging.getLogger(__name__)


def _error_json(code: str, message: str, status_code: int, details: dict | None = None) -> JSONResponse:
    body: dict = {"success": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register standardized exception handlers on any FastAPI app.
    Call once during app creation. All services get identical error shapes.

    Handles the full AppError hierarchy + FastAPI validation errors + unhandled.
    """

    @app.exception_handler(ValidationError)
    async def validation_app_error(_req: Request, exc: ValidationError) -> JSONResponse:
        details = {"errors": exc.errors} if exc.errors else None
        return _error_json(exc.code, exc.message, exc.status_code, details)

    @app.exception_handler(ServiceError)
    async def service_error(_req: Request, exc: ServiceError) -> JSONResponse:
        details = exc.service_error if exc.service_error else None
        return _error_json(exc.code, exc.message, exc.status_code, details)

    @app.exception_handler(PipelineError)
    async def pipeline_error(_req: Request, exc: PipelineError) -> JSONResponse:
        details = {}
        if exc.task_index is not None:
            details["task_index"] = exc.task_index
        if exc.task_type:
            details["task_type"] = exc.task_type
        if exc.service_error:
            details["service_error"] = exc.service_error
        return _error_json(exc.code, exc.message, exc.status_code, details or None)

    @app.exception_handler(AppError)
    async def app_error(_req: Request, exc: AppError) -> JSONResponse:
        """Catch-all for any AppError subclass not handled above."""
        return _error_json(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(_req: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err.get("loc", []))
            errors.append({"field": loc, "message": err.get("msg", "")})
        return _error_json(
            "VALIDATION_ERROR", "Request validation failed.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"errors": errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_error(_req: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return _error_json("INTERNAL_ERROR", "An unexpected error occurred.", 500)
