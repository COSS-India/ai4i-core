from pydantic import BaseModel , EmailStr, Field , Field
from uuid import UUID
from typing import Dict , Any


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
    quotas: Dict[str , Any]
    created_at: str
    updated_at: str

    
    model_config = {
        "populate_by_name": True
    }
