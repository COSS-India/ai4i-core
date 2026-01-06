from pydantic import BaseModel, Field
from uuid import UUID
from decimal import Decimal


class BillingUpdateRequest(BaseModel):
    tenant_id: UUID
    billing_plan: Decimal = Field(..., gt=0, description="Billing amount in INR")


class BillingUpdateResponse(BaseModel):
    tenant_id: UUID
    billing_customer_id: str
    billing_plan: Decimal
    billing_status: str