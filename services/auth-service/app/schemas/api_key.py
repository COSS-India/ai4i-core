"""
API key request/response schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# ── Requests ──

class APIKeyCreateRequest(BaseSchema):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: list[str] = Field(default_factory=list, description="Permission names")
    tenant_id: Optional[UUID] = Field(None, description="Tenant ID for tenant-scoped API keys")


class APIKeyUpdateRequest(BaseSchema):
    key_name: Optional[str] = Field(None, min_length=1, max_length=100)
    permissions: Optional[list[str]] = None
    is_active: Optional[bool] = None


class APIKeyValidationRequest(BaseSchema):
    api_key: str
    service: str = Field(..., description="Service name: asr, tts, nmt, pipeline, model-management")
    action: str = Field(..., description="Action type: read, inference")
    user_id: Optional[UUID] = Field(None, description="Authenticated user ID for ownership enforcement.")


# ── Responses ──

class APIKeyResponse(BaseSchema):
    key_id: int
    key_name: str
    tenant_id: Optional[UUID] = None
    permissions: list[str]
    is_active: bool
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


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
