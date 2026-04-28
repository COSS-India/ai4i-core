"""
User request/response schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


class CreationType(str, Enum):
    DIRECT = "direct"
    GOOGLE = "google"
    TENANT = "tenant"


class UserUpdate(BaseSchema):
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    timezone: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = Field(None, max_length=500)


class UserResponse(BaseSchema):
    user_id: UUID
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_delete: Optional[bool] = None
    is_tenant_active: Optional[bool] = None
    creation_type: Optional[CreationType] = None
    tenant_id: Optional[int] = Field(None, description="Tenant identifier")
    last_login: Optional[datetime] = None
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = None
    timezone: Optional[str] = None
    roles: list[str] = []
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class UserDetailResponse(BaseSchema):
    """Admin view of user details."""
    user_id: UUID
    username: str
    email: EmailStr
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    is_delete: Optional[bool] = None
    is_tenant_active: Optional[bool] = None
    creation_type: Optional[CreationType] = None
    tenant_id: Optional[int] = None
    created_at: datetime
    last_login: Optional[datetime] = None


class UserListResponse(BaseSchema):
    """Compact user list item."""
    user_id: UUID
    username: str
    email: EmailStr
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    creation_type: Optional[CreationType] = None
