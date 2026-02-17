from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from .tenant_create import QuotaStructure
from .services_update import FieldChange
from .user_create import _validate_role


class TenantUpdateRequest(BaseModel):
    """Request model for updating tenant information"""
    tenant_id: str = Field(..., description="Tenant identifier")
    organization_name: Optional[str] = Field(None, min_length=2, max_length=255, description="Organization name")
    contact_email: Optional[str] = Field(None, description="Contact email address")
    domain: Optional[str] = Field(None, min_length=3, max_length=255, description="Domain name")
    requested_quotas: Optional[QuotaStructure] = Field(None, description="Requested quota limits (characters_length, audio_length_in_min)")
    usage_quota: Optional[QuotaStructure] = Field(None, description="Usage quota values (characters_length, audio_length_in_min)")
    role: Optional[str] = Field(
        None,
        description="Role for tenant admin (key-value: {'role': 'ADMIN'}). Allowed: ADMIN, USER, GUEST, MODERATOR.",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        return _validate_role(v)


class TenantUpdateResponse(BaseModel):
    """Response model for tenant update"""
    tenant_id: str
    message: str
    changes: Dict[str, FieldChange]
    updated_fields: list[str]
    role: Optional[str] = Field(
        None,
        description="Current tenant admin role after update (key-value: {'role': 'ADMIN'}).",
    )
