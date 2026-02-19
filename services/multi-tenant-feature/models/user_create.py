from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import List, Optional

from .enum_tenant import TenantUserRole

ALLOWED_ROLES = {r.value for r in TenantUserRole}


def _validate_role(v: Optional[str]) -> Optional[str]:
    """Validate role is one of ADMIN, USER, GUEST, MODERATOR."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    val = v.strip().upper()
    if val not in ALLOWED_ROLES:
        raise ValueError(f"role must be one of: {', '.join(sorted(ALLOWED_ROLES))}")
    return val


class UserRegisterRequest(BaseModel):
    tenant_id: str = Field(..., example="acme-corp-5d448a")
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: str = Field(None, max_length=150)
    phone_number: Optional[str] = Field(None, max_length=20, description="User phone number")
    services: List[str] = Field(..., example=["tts", "asr"])
    is_approved: bool = Field(False, description="Indicates if the user is approved by tenant admin")
    role: Optional[str] = Field(
        None,
        description="Role for the user. Key-value: {'role': 'USER'}. Allowed: ADMIN, USER, GUEST, MODERATOR.",
        example="USER",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        return _validate_role(v)


class UserRegisterResponse(BaseModel):
    user_id: int
    tenant_id: str
    username: str
    email: str
    services: List[str]
    schema: str
    created_at: datetime
    role: str = Field(
        ...,
        description="Role for the user (key-value: {'role': 'USER'}). One of: ADMIN, USER, GUEST, MODERATOR.",
    )
