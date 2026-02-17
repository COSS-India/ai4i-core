from pydantic import BaseModel
from uuid import UUID


class TenantSendEmailVerificationRequest(BaseModel):
    """Request model for sending initial email verification link."""
    tenant_id: str  # Tenant identifier string (e.g., 'acme-corp')


class TenantSendEmailVerificationResponse(BaseModel):
    """Response model for sending initial email verification link."""
    tenant_uuid: UUID
    tenant_id: str
    token: str
    message: str


class TenantResendEmailVerificationRequest(BaseModel):
    """Request model for resending email verification link."""
    tenant_id: str  # Tenant identifier string (e.g., 'acme-corp')


class TenantResendEmailVerificationResponse(BaseModel):
    """Response model for resending email verification link."""
    tenant_uuid: UUID
    tenant_id: str
    token: str
    message: str