"""
API key request/response schemas.
"""

from datetime import datetime
from typing import Optional

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


class ValidateAPIKeyResponse(BaseSchema):
    valid: bool = True
    user_id: Optional[str] = None
    
    permission_ids: list[int] = []
    token_type: str = "api_key"


class ValidateAPIKeyErrorResponse(BaseSchema):
    valid: bool = False
    error: str
    message: str
