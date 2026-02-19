from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from uuid import UUID
from .enum_tenant import SubscriptionType
from .user_create import _validate_role


class QuotaStructure(BaseModel):
    """Structure for quota limits"""
    characters_length: Optional[int] = Field(None, ge=0, description="Character length quota")
    audio_length_in_min: Optional[int] = Field(None, ge=0, description="Audio length quota in minutes")


class TenantRegisterRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=255)
    domain: str = Field(..., min_length=3, max_length=255)  # user supplied domain
    contact_email: EmailStr
    phone_number: Optional[str] = Field(None, max_length=20, description="Contact phone number")
    requested_subscriptions: Optional[List[SubscriptionType]] = Field(default=[], description="List of requested service subscriptions, e.g. ['tts', 'asr']")
    requested_quotas: Optional[QuotaStructure] = Field(None, description="Requested quota limits for the tenant")
    usage_quota: Optional[QuotaStructure] = Field(None, description="Initial usage quota values")


class TenantRegisterResponse(BaseModel):
    id: UUID
    tenant_id: str
    # subdomain: Optional[str] = None
    schema_name: str
    subscriptions: List[str]
    quotas: Dict[str, Any]
    usage_quota: Optional[Dict[str, Any]] = None
    status: str
    message: Optional[str] = None