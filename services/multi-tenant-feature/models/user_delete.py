from pydantic import BaseModel, Field


class TenantUserDeleteRequest(BaseModel):
    """Request model for deleting a tenant user."""

    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")


class TenantUserDeleteResponse(BaseModel):
    """Response model for tenant user deletion."""

    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")
    message: str = Field(..., description="Deletion message")

