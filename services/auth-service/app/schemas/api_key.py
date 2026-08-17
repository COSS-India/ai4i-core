"""
API key request/response schemas.
"""

from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field

from app.schemas.base import BaseSchema
from app.schemas.common import SuccessResponse


# ── Requests ──

class CreateAPIKeyRequest(BaseSchema):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Stable permission names (e.g. nmt.inference). At least one "
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
    permissions: Optional[list[str]] = Field(
        None,
        min_length=1,
        description=(
            "Omit to leave permissions unchanged. If supplied, must contain at "
            "least one permission name — an explicit empty list is rejected (same "
            "as create) since a zero-permission key can't authorize anything."
        ),
    )
    expires_days: Optional[int] = Field(None, ge=1)


# ── Response payloads (the ``data`` field) ──

class CreateAPIKeyData(BaseSchema):
    id: int
    api_key: str = Field(..., description="32-char hex key. Store securely — shown only once.")
    key_name: str
    permissions: list[str]
    expires_at: Optional[datetime] = None


class APIKeyItem(BaseSchema):
    """Masked API key as returned on list and update."""

    id: int
    key_name: str
    api_key: str = Field(
        ...,
        description="Masked key (first 4 and last 4 characters). The raw key is never returned after create.",
    )
    user_id: str
    permissions: list[str]
    expires_at: Optional[datetime] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class APIKeyListData(BaseSchema):
    api_keys: list[APIKeyItem]


class APIKeyAdminItem(APIKeyItem):
    """List-all item: masked key plus masked owner identity."""

    user_email: Optional[str] = Field(
        None,
        description="Masked owner email. Plaintext PII is never returned.",
    )
    username: Optional[str] = None


class RevokeAPIKeyData(BaseSchema):
    message: str


# ── Route responses: inherit SuccessResponse and override ``data`` ──

class CreateAPIKeyResponse(SuccessResponse):
    """POST /auth/api-keys"""

    data: CreateAPIKeyData


class ListAPIKeysResponse(SuccessResponse):
    """GET /auth/api-keys"""

    data: APIKeyListData


class UpdateAPIKeyResponse(SuccessResponse):
    """PATCH /auth/api-keys/{key_id}"""

    data: APIKeyItem


class RevokeAPIKeyResponse(SuccessResponse):
    """DELETE /auth/api-keys/{key_id}"""

    data: RevokeAPIKeyData


class ListAllAPIKeysResponse(SuccessResponse):
    """GET /auth/api-keys/all"""

    data: list[APIKeyAdminItem]


class ValidateAPIKeyResponse(BaseSchema):
    valid: bool = True
    user_id: Optional[str] = None
    permission_ids: list[int] = []
    token_type: str = "api_key"


class ValidateAPIKeyErrorResponse(BaseSchema):
    valid: bool = False
    error: str
    message: str
