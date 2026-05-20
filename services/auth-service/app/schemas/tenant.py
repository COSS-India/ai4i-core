"""
Tenant request/response schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Union
from uuid import UUID

from pydantic import AliasChoices, EmailStr, Field, field_serializer, model_validator

from app.models.user import CreationType
from app.schemas.base import BaseSchema
from app.models.tenant import TenantStatus


class TenantUserRole(str, Enum):
    """Roles assignable to users provisioned under a tenant."""

    USER = "USER"
    TENANT_ADMIN = "TENANT ADMIN"


class TenantCreate(BaseSchema):
    contact_name: str = Field(..., min_length=1, max_length=255)
    organisation: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone_number: Optional[str] = Field(None, max_length=20)


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
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    role: TenantUserRole = TenantUserRole.USER


class TenantUserCreateResponse(BaseSchema):
    user_id: str
    setup_token: str
    message: str = "Tenant user provisioned. Share the setup link to complete onboarding."


class TenantUserStatusUpdate(BaseSchema):
    is_active: Optional[bool] = None
    is_tenant_active: Optional[bool] = None

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

    user_id: UUID = Field(validation_alias=AliasChoices("user_id", "id"))
    username: str
    email: EmailStr
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    is_tenant_active: Optional[bool] = None
    creation_type: Optional[CreationType] = None
    role: TenantUserRole
