from pydantic import BaseModel , Field
from typing import Optional

class TenantSubscriptionAddRequest(BaseModel):
    tenant_id: str
    subscriptions: list[str] = Field(..., min_items=1)



class TenantSubscriptionRemoveRequest(BaseModel):
    tenant_id: str
    subscriptions: list[str] = Field(..., min_items=1)



class TenantSubscriptionResponse(BaseModel):
    tenant_id: str
    subscriptions: list[str]
    # Optional human-readable message for partial success cases (e.g. duplicates).
    message: Optional[str] | None = None