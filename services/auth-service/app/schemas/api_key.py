"""
API key request/response schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


# ── Requests ──

class APIKeyCreateRequest(BaseSchema):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: list[int] = Field(default_factory=list, description="Permission IDs")
    expires_days: Optional[int] = Field(None, ge=1, le=365)


class APIKeyUpdateRequest(BaseSchema):
    key_name: Optional[str] = Field(None, min_length=1, max_length=100)
    permissions: Optional[list[int]] = None
    is_active: Optional[bool] = None


class APIKeyValidationRequest(BaseSchema):
    api_key: str
    service: str = Field(..., description="Service name: asr, tts, nmt, pipeline, model-management")
    action: str = Field(..., description="Action type: read, inference")
    user_id: Optional[UUID] = Field(None, description="Authenticated user ID for ownership enforcement.")


# ── Responses ──

class APIKeyResponse(BaseSchema):
    key_id: int = Field(validation_alias="id")
    key_name: str
    user_id: UUID
    # Model stores {"permission": [id, ...]}; extract to a flat list of int IDs.
    permissions: list[int] = []
    is_active: bool
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    @field_validator("permissions", mode="before")
    @classmethod
    def extract_permission_ids(cls, v) -> list:
        if isinstance(v, dict):
            return v.get("permission", [])
        if isinstance(v, list):
            return v
        return []


class APIKeyCreateResponse(APIKeyResponse):
    """Returned on creation only — includes the full API key (shown once)."""
    api_key: str = Field(..., description="Full API key. Store securely — shown only once.")


class APIKeyListResponse(BaseSchema):
    api_keys: list[APIKeyResponse]


class APIKeyValidationResponse(BaseSchema):
    valid: bool
    message: Optional[str] = None
    user_id: Optional[UUID] = None
    permissions: list[str] = []
