"""
API key request/response schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# ── Requests ──

class CreateAPIKeyRequest(BaseSchema):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: list[int] = Field(default_factory=list, description="Permission IDs from the permissions table")
    expires_days: Optional[int] = Field(None, ge=1, description="Key lifetime in days; defaults to API_KEY_EXPIRE_DAYS")


class UpdateAPIKeyRequest(BaseSchema):
    api_key: str = Field(..., min_length=32, max_length=32, description="Hex key to update")
    key_name: Optional[str] = Field(None, min_length=1, max_length=100)
    permissions: Optional[list[int]] = None
    expires_days: Optional[int] = Field(None, ge=1)


# ── Responses ──

class CreateAPIKeyResponse(BaseSchema):
    api_key: str = Field(..., description="32-char hex key. Store securely — shown only once.")
    key_name: str
    permissions: list[int]
    expires_at: Optional[datetime] = None


class APIKeyItem(BaseSchema):
    key_name: str
    user_id: UUID
    permissions: list[int]
    expires_at: Optional[datetime] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ListAPIKeyResponse(BaseSchema):
    api_keys: list[APIKeyItem]


class AdminAPIKeyItem(APIKeyItem):
    user_email: str
    username: str


class AdminListAPIKeyResponse(BaseSchema):
    api_keys: list[AdminAPIKeyItem]


class ValidateAPIKeyResponse(BaseSchema):
    valid: bool = True
    user_id: Optional[str] = None
    
    permission_ids: list[int] = []
    token_type: str = "api_key"


class ValidateAPIKeyErrorResponse(BaseSchema):
    valid: bool = False
    error: str
