"""
User request/response schemas.
"""

from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, EmailStr, Field

from app.models.user import CreationType
from app.schemas.base import BaseSchema


class UserUpdate(BaseSchema):
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    timezone: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = Field(None, max_length=500)


class UserListResponse(BaseSchema):
    """Compact user list item."""
    user_id: UUID = Field(validation_alias=AliasChoices("user_id", "id"))
    username: str
    email: EmailStr
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    creation_type: Optional[CreationType] = None
