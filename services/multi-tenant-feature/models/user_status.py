from pydantic import BaseModel
from .enum_tenant import TenantUserStatus



class TenantUserStatusUpdateRequest(BaseModel):
    tenant_id: str
    user_id: int
    status: TenantUserStatus


class TenantUserStatusUpdateResponse(BaseModel):
    tenant_id: str
    user_id: int
    old_status: TenantUserStatus
    new_status: TenantUserStatus