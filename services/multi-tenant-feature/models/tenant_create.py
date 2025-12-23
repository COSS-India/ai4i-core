from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from uuid import UUID
from .enum_tenant import SubscriptionType

class TenantRegisterRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=255)
    domain: str = Field(..., min_length=3, max_length=255)  # user supplied domain
    contact_email: EmailStr
    requested_subscriptions: Optional[List[SubscriptionType]] = []  # e.g. ["tts","asr"]
    requested_quotas: Optional[Dict[str, Any]] = None

class TenantRegisterResponse(BaseModel):
    id: UUID
    tenant_id: str
    subdomain: Optional[str] = None
    schema_name: str
    subscriptions: List[str]
    quotas : Dict[str , Any]
    status: str
    token: str
    message: Optional[str] = None