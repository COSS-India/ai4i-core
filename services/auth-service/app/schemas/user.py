"""
User request/response schemas.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import AliasChoices, EmailStr, Field, field_validator

from app.models.user import CreationType
from app.schemas.base import BaseSchema
from app.schemas.common import SuccessResponse
from app.schemas.text_validators import check_name_chars, clean_text


class UserUpdate(BaseSchema):
    # Same rules TenantUserUpdate applies to this column (tenant.py): cleaned
    # of invisible characters and restricted to name-like text, so a value
    # accepted on one path can't be rejected on another.
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    timezone: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = Field(None, max_length=500)

    @field_validator("full_name", mode="before")
    @classmethod
    def _clean_full_name(cls, v: Any) -> Any:
        return clean_text(v)

    @field_validator("full_name", mode="after")
    @classmethod
    def _validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return check_name_chars(v)
        return v


class UserListResponse(BaseSchema):
    """Compact user list item."""
    # ORM exposes ``id``; API responses use ``user_id`` (field name).
    user_id: UUID = Field(validation_alias=AliasChoices("id", "user_id"))
    username: str
    email: str
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    creation_type: Optional[CreationType] = None


class UserProfileData(BaseSchema):
    """Full profile from GET /auth/me, PUT /auth/me, and GET /auth/users/{user_id}."""

    user_id: str
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_tenant_active: Optional[bool] = None
    creation_type: Optional[str] = None
    tenant_id: Optional[str] = None
    last_login: Optional[datetime] = None
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = None
    timezone: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GetMeResponse(SuccessResponse):
    """GET /auth/me"""

    data: UserProfileData


class UpdateMeResponse(SuccessResponse):
    """PUT /auth/me"""

    data: UserProfileData


class ListUsersResponse(SuccessResponse):
    """GET /auth/users"""

    data: list[UserListResponse]


class GetUserResponse(SuccessResponse):
    """GET /auth/users/{user_id}"""

    data: UserProfileData
