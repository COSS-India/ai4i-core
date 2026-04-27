"""
Tenant request/response schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema
from app.models.tenant import TenantStatus


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
    tenant_id: UUID
    contact_name: str
    organisation: str
    email: str
    phone_number: Optional[str] = None
    status: TenantStatus
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class TenantUserCreate(BaseSchema):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)


class TenantUserCreateResponse(BaseSchema):
    user_id: str
    setup_token: str
    message: str = "Tenant user provisioned. Share the setup link to complete onboarding."


class TenantUserStatusUpdate(BaseSchema):
    is_active: Optional[bool] = None
    is_tenant_active: Optional[bool] = None


class TenantUserUpdate(BaseSchema):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    username: Optional[str] = Field(None, min_length=3, max_length=100)
