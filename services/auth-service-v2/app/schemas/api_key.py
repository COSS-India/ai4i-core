"""
API key request/response schemas.
"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSchema


# ── Requests ──

class APIKeyCreateRequest(BaseSchema):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: list[int] = Field(default_factory=list, description="Permission IDs")
    expires_days: Optional[int] = Field(None, ge=1, le=365)
    user_id: Optional[int] = Field(
        None,
        alias="userId",
        description="User ID for admin-created keys. If not provided, creates for current user.",
    )


class APIKeyUpdateRequest(BaseSchema):
    key_name: Optional[str] = Field(None, min_length=1, max_length=100)
    permissions: Optional[list[str]] = None
    is_active: Optional[bool] = None


class APIKeySelectRequest(BaseSchema):
    api_key_id: Optional[int] = Field(
        None, description="API key ID to mark as selected."
    )


class APIKeyValidationRequest(BaseSchema):
    api_key: str
    service: str = Field(..., description="Service name: asr, tts, nmt, pipeline, model-management")
    action: str = Field(..., description="Action type: read, inference")
    user_id: Optional[int] = Field(None, description="Authenticated user ID for ownership enforcement.")


# ── Responses ──

class APIKeyResponse(BaseSchema):
    id: int
    key_name: str
    permissions: list[str]
    is_active: bool
    is_revoked: bool = False
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None


class APIKeyCreateResponse(APIKeyResponse):
    """Returned on creation only — includes the full JWT token (shown once)."""
    api_key: str = Field(..., description="Full JWT API key. Store securely — shown only once.")


class APIKeyListResponse(BaseSchema):
    selected_api_key_id: Optional[int] = None
    api_keys: list[APIKeyResponse]


class AdminAPIKeyWithUserResponse(APIKeyResponse):
    """API key details with owning user info (admin view)."""
    user_id: int
    user_email: str
    username: str


class APIKeyValidationResponse(BaseSchema):
    valid: bool
    message: Optional[str] = None
    user_id: Optional[int] = None
    permissions: list[str] = []
