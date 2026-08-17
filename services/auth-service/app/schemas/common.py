"""Shared OpenAPI response envelopes for auth-service routes."""

from typing import Any

from app.schemas.base import BaseSchema


class SuccessResponse(BaseSchema):
    """Common success envelope: ``{"success": true, "data": ...}``.

    Route schemas subclass this and override ``data`` with the payload type.
    """

    success: bool = True
    data: Any


class ErrorDetail(BaseSchema):
    """Inner object of every handler error body: ``{code, message, timestamp}``."""

    code: str
    message: str
    timestamp: float


class ErrorResponse(BaseSchema):
    """Wire format of auth-service errors: ``{"detail": {code, message, timestamp}}``."""

    detail: ErrorDetail


_ERROR_DESCRIPTIONS = {
    401: "Not authenticated.",
    403: "Not authorized.",
    404: "Not found.",
    422: "Validation error.",
    503: "Service unavailable.",
}


def error_responses(*status_codes: int) -> dict[int, dict[str, Any]]:
    """Attach the common ``ErrorResponse`` schema to the given HTTP statuses."""
    return {
        code: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS[code]}
        for code in status_codes
    }
