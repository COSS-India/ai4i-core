"""Shared OpenAPI response envelopes for auth-service routes."""

from typing import Any

from ai4i_core.exceptions import ErrorDetail
from app.schemas.base import BaseSchema


class SuccessResponse(BaseSchema):
    """Common success envelope: ``{"success": true, "data": ...}``.

    Route schemas subclass this and override ``data`` with the payload type.
    """

    success: bool = True
    data: Any


class MessageData(BaseSchema):
    """Payload for enveloped responses that only confirm an action: ``{"message": "..."}``."""

    message: str


class ErrorResponse(BaseSchema):
    """Wire format of auth-service errors: ``{"detail": {code, message, timestamp}}``.

    Reuses ai4i_core's ``ErrorDetail`` (``code``/``timestamp`` optional, defaulted)
    rather than redeclaring a narrower copy — the handlers in
    ``ai4i_core.exceptions.handlers`` don't always populate every field (e.g. a
    raw ``HTTPException(detail={"code", "message"})`` never gets a timestamp),
    so this must stay no stricter than what those handlers actually emit.
    """

    detail: ErrorDetail


_ERROR_DESCRIPTIONS = {
    401: "Not authenticated.",
    403: "Not authorized.",
    404: "Not found.",
    409: "Conflict.",
    422: "Validation failed.",
    503: "Service unavailable.",
}


def error_responses(*status_codes: int) -> dict[int, dict[str, Any]]:
    """Attach the common ``ErrorResponse`` schema to the given HTTP statuses."""
    return {
        code: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS[code]}
        for code in status_codes
    }
