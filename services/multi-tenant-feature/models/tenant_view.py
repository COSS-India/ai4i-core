from pydantic import BaseModel , EmailStr, Field
from uuid import UUID
from typing import Dict , Any, Optional, List


class TenantViewResponse(BaseModel):
    id: UUID
    tenant_id: str
    user_id: int
    organization_name: str
    email: EmailStr
    domain: str
    schema_name: str = Field(..., alias="schema")
    subscriptions: list[str]
    status: str
    quotas: Dict[str, Any]
    usage_quota: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str

    
    model_config = {
        "populate_by_name": True
    }


class ListTenantsResponse(BaseModel):
    """Response model for listing all tenants"""
    count: int = Field(..., description="Total number of tenants")
    tenants: List[TenantViewResponse] = Field(..., description="List of tenant details")
