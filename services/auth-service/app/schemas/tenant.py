"""
Tenant request/response schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


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
    status: Optional[str] = Field(None, max_length=50)


class TenantResponse(BaseSchema):
    tenant_id: UUID
    contact_name: str
    organisation: str
    email: str
    phone_number: Optional[str] = None
    status: str
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
