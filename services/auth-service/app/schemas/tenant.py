"""
Tenant request/response schemas.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Optional, Union
from uuid import UUID

from pydantic import AliasChoices, EmailStr, Field, StrictBool, field_serializer, field_validator, model_validator

from app.models.user import CreationType
from app.schemas.base import BaseSchema
from app.models.tenant import TenantStatus

# Invisible Unicode characters that str.strip() does not remove:
# soft hyphen, zero-width space/non-joiner/joiner, LTR/RTL marks,
# line/paragraph separators, zero-width no-break space (BOM).
_INVISIBLE_CHARS = re.compile(
    "[\u00ad\u200b\u200c\u200d\u200e\u200f\u2028\u2029\ufeff]+"
)


class TenantUserRole(str, Enum):
    """Roles assignable to users provisioned under a tenant."""

    USER = "USER"
    TENANT_ADMIN = "TENANT ADMIN"


class TenantCreate(BaseSchema):
    contact_name: str = Field(..., min_length=1, max_length=255)
    organisation: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone_number: Optional[str] = Field(None, max_length=20)
    plan_id: Optional[UUID] = None


class TenantUpdate(BaseSchema):
    contact_name: Optional[str] = Field(None, min_length=1, max_length=255)
    organisation: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, max_length=20)
    status: Optional[TenantStatus] = None


class TenantStatusUpdate(BaseSchema):
    status: TenantStatus


class TenantResponse(BaseSchema):
    tenant_id: int = Field(validation_alias="id")
    contact_name: str = Field(validation_alias="name")
    organisation: str
    email: str
    phone_number: Optional[str] = None
    status: TenantStatus

    @field_serializer("status")
    def _status_as_api_value(self, value: Union[TenantStatus, str]) -> str:
        if isinstance(value, TenantStatus):
            return value.value
        return str(value).strip().upper()

    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None


class TenantUserCreate(BaseSchema):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    role: TenantUserRole = TenantUserRole.USER

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_full_name(cls, v: str) -> str:
        if isinstance(v, str):
            return _INVISIBLE_CHARS.sub("", v).strip()
        return v


class TenantUserCreateResponse(BaseSchema):
    user_id: str
    setup_token: str
    message: str = "Tenant user provisioned. Share the setup link to complete onboarding."


class TenantUserStatusUpdate(BaseSchema):
    is_active: Optional[StrictBool] = None
    is_tenant_active: Optional[StrictBool] = None

    @model_validator(mode='before')
    @classmethod
    def reject_explicit_null(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if 'is_active' in data and data['is_active'] is None:
                raise ValueError("is_active cannot be null; provide true or false.")
            if 'is_tenant_active' in data and data['is_tenant_active'] is None:
                raise ValueError("is_tenant_active cannot be null; provide true or false.")
        return data

    @model_validator(mode='after')
    def at_least_one_field(self) -> 'TenantUserStatusUpdate':
        if self.is_active is None and self.is_tenant_active is None:
            raise ValueError("Provide at least one of is_active or is_tenant_active.")
        return self


class TenantUserUpdate(BaseSchema):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    role: Optional[TenantUserRole] = None

    @model_validator(mode='after')
    def at_least_one_field(self) -> 'TenantUserUpdate':
        if not any([self.email, self.full_name, self.phone_number, self.username, self.role is not None]):
            raise ValueError("Provide at least one field to update.")
        return self


class TenantUserResponse(BaseSchema):
    """Tenant-scoped user list/detail item including assignable role."""

    # ORM exposes ``id``; API responses use ``user_id`` (field name).
    user_id: UUID = Field(validation_alias=AliasChoices("id", "user_id"))
    username: str
    email: EmailStr
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    is_tenant_active: Optional[bool] = None
    creation_type: Optional[CreationType] = None
    role: TenantUserRole
