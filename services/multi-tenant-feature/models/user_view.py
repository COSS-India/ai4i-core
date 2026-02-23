from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from typing import List, Optional


class TenantUserViewResponse(BaseModel):
    id: UUID
    user_id: int
    tenant_id: str
    username: str
    email: EmailStr
    phone_number: Optional[str] = None
    subscriptions: list[str]
    status: str
    created_at: str
    updated_at: str
    role: str = Field(
        "",
        description="Single role for the user, e.g. 'USER' or 'ADMIN'. Only one role is allowed per user.",
    )


class ListUsersResponse(BaseModel):
    """Response model for listing all tenant users"""
    count: int = Field(..., description="Total number of users")
    users: List[TenantUserViewResponse] = Field(..., description="List of user details")