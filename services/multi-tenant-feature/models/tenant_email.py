from pydantic import BaseModel
from uuid import UUID


class TenantResendEmailVerificationRequest(BaseModel):
    tenant_id: str


class TenantResendEmailVerificationResponse(BaseModel):
    tenant_uuid: UUID
    tenant_id: str
    token: str
    message: str