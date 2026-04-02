from pydantic import BaseModel, Field
from .enum_tenant import SubscriptionType
from typing import Optional

class UserSubscriptionAddRequest(BaseModel):
    tenant_id: str
    user_id: int
    subscriptions: list[SubscriptionType] = Field(..., min_items=1)


class UserSubscriptionRemoveRequest(BaseModel):
    tenant_id: str
    user_id: int
    subscriptions: list[SubscriptionType] = Field(..., min_items=1)


class UserSubscriptionResponse(BaseModel):
    tenant_id: str
    user_id: int
    subscriptions: list[str]
    # Optional human-readable message for partial success cases (e.g. duplicates).
    message: Optional[str] | None = None

