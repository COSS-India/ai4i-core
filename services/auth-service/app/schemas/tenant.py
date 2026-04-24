"""
Tenant request/response schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema


class TenantCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    organisation: str = Field(..., min_length=1, max_length=255)
    org_email: EmailStr
    org_phone_number: Optional[str] = Field(None, max_length=20)


class TenantUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    organisation: Optional[str] = Field(None, min_length=1, max_length=255)
    org_email: Optional[EmailStr] = None
    org_phone_number: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=50)


class TenantResponse(BaseSchema):
    tenant_id: UUID
    name: str
    organisation: str
    org_email: str
    org_phone_number: Optional[str] = None
    status: str
    created_at: datetime
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
