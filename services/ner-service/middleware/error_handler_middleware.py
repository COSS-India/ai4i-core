"""
Error handler middleware registration for NER service.

Copied from OCR service to keep behavior consistent.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def add_error_handlers(app: FastAPI) -> None:
    """Register common error handlers on the FastAPI app."""

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "message": str(exc),
            },
        )



