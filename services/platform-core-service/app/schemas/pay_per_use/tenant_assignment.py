from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TierAssignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to assign the tier to")
    tier_id: str = Field(..., description="UUID of the PPU tier to assign")
    budget: Decimal = Field(..., ge=0, description="Budget limit in INR (paise precision)")


class TierAssignResponse(BaseModel):
    tenant_id: str
    tier_id: str
    tier_name: str
    budget_limit: Decimal
    available_balance: Decimal
    effective_from: datetime
    effective_to: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
