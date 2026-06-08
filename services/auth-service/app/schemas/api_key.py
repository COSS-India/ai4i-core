"""
API key request/response schemas.
"""

from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field

from app.schemas.base import BaseSchema


# ── Requests ──

class CreateAPIKeyRequest(BaseSchema):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: list[int] = Field(
        ...,
        min_length=1,
        description=(
            "Permission IDs from the permissions table. At least one "
            "permission is required — an API key with no permissions cannot "
            "authorize any request and would only be confusing to the caller."
        ),
    )
    expires_days: Optional[int] = Field(None, ge=1, description="Key lifetime in days; defaults to API_KEY_EXPIRE_DAYS")


class UpdateAPIKeyRequest(BaseSchema):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="forbid",
    )

    key_name: Optional[str] = Field(None, min_length=1, max_length=100)
    permissions: Optional[list[int]] = Field(
        None,
        min_length=1,
        description=(
            "Omit to leave permissions unchanged. If supplied, must contain at "
            "least one permission ID — an explicit empty list is rejected (same "
            "as create) since a zero-permission key can't authorize anything."
        ),
    )
    expires_days: Optional[int] = Field(None, ge=1)


# ── Responses ──

class CreateAPIKeyResponse(BaseSchema):
    api_key: str = Field(..., description="32-char hex key. Store securely — shown only once.")
    key_name: str
    permissions: list[int]
    expires_at: Optional[datetime] = None


class ValidateAPIKeyResponse(BaseSchema):
    valid: bool = True
    user_id: Optional[str] = None
    permission_ids: list[int] = []
    token_type: str = "api_key"


class ValidateAPIKeyErrorResponse(BaseSchema):
    valid: bool = False
    error: str
    message: str
