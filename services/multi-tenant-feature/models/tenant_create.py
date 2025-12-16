from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from uuid import UUID

class TenantRegisterRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=255)
    domain: str = Field(..., min_length=3, max_length=255)  # user supplied domain
    contact_email: EmailStr
    requested_subscriptions: Optional[List[str]] = []  # e.g. ["tts","asr"]
    requested_quotas: Optional[Dict[str, Any]] = None
    billing_plan: float = Field(0.00, gt=0, description="Billing amount in INR")

class TenantRegisterResponse(BaseModel):
    id: UUID
    tenant_id: str
    subdomain: str
    schema_name: str
    validation_time: datetime
    status: str
    token: str