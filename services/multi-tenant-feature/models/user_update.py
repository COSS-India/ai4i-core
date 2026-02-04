from typing import Optional, Dict, Any, List

from pydantic import BaseModel, EmailStr, Field

from .services_update import FieldChange


class TenantUserUpdateRequest(BaseModel):
    """Request model for updating tenant user information."""

    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")
    username: Optional[str] = Field(None,min_length=3,max_length=100,description="Username for the tenant user")
    email: Optional[EmailStr] = Field(None,description="Email address for the tenant user")
    is_approved: Optional[bool] = Field(None,description="Whether the tenant user is approved by the tenant admin")


class TenantUserUpdateResponse(BaseModel):
    """Response model for tenant user update."""

    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: int = Field(..., description="Auth user id for tenant user")
    message: str = Field(..., description="Update message")
    changes: Dict[str, FieldChange] = Field(..., description="Dictionary of field changes")
    updated_fields: List[str] = Field(..., description="List of updated field names")

