from pydantic import BaseModel , EmailStr
from uuid import UUID

class TenantUserViewResponse(BaseModel):
    id: UUID
    user_id: int
    tenant_id: str
    username: str
    email: EmailStr
    subscriptions: list[str]
    status: str
    created_at: str
    updated_at: str