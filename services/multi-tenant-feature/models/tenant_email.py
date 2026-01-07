from pydantic import BaseModel
from uuid import UUID


class TenantResendEmailVerificationRequest(BaseModel):
    tenant_id: UUID # UUID as string


class TenantResendEmailVerificationResponse(BaseModel):
    tenant_uuid: UUID
    tenant_id: str
    token: str
    message: str