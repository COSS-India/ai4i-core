"""
User request/response schemas.
"""

from datetime import datetime
from typing import Optional

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


class UserUpdate(BaseSchema):
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    timezone: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, max_length=10)
    preferences: Optional[dict] = None


class UserResponse(BaseSchema):
    id: int
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    is_superuser: bool
    is_tenant: Optional[bool] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    avatar_url: Optional[str] = None
    roles: list[str] = []
    tenant_id: Optional[str] = Field(None, description="Tenant identifier")


class UserDetailResponse(BaseSchema):
    """Admin view of user details."""
    userid: int = Field(..., alias="id")
    username: str
    emailid: str = Field(..., alias="email")
    phonenumber: Optional[str] = Field(None, alias="phone_number")
    full_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class UserListResponse(BaseSchema):
    """Compact user list item."""
    userid: int = Field(..., alias="id")
    username: str
    emailid: str = Field(..., alias="email")
    phonenumber: Optional[str] = Field(None, alias="phone_number")
