from pydantic import BaseModel, Field
from typing import Optional
from .enum_tenant import TenantStatus
from datetime import date


class TenantStatusUpdateRequest(BaseModel):
    tenant_id: str
    status: TenantStatus
    reason: Optional[str] = Field(None, description="Provide Reason if changing to SUSPENDED status")
    suspended_until: Optional[date] = Field(None, description="Optional suspension end date in ISO format (YYYY-MM-DD)")

class TenantStatusUpdateResponse(BaseModel):
    tenant_id: str
    old_status: TenantStatus
    new_status: TenantStatus
