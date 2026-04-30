from pydantic import BaseModel , Field

class TenantSubscriptionAddRequest(BaseModel):
    tenant_id: str
    subscriptions: list[str] = Field(..., min_items=1)



class TenantSubscriptionRemoveRequest(BaseModel):
    tenant_id: str
    subscriptions: list[str] = Field(..., min_items=1)



class TenantSubscriptionResponse(BaseModel):
    tenant_id: str
    subscriptions: list[str]