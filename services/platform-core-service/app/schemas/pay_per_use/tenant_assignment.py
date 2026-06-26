from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TierAssignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to assign the tier to")
    tier_id: str = Field(..., description="UUID of the PPU tier to assign")
    budget: Decimal = Field(..., ge=0, max_digits=15, decimal_places=4, description="Budget limit in INR (paise precision)")
    effective_from: datetime = Field(..., description="Assignment start date (UTC)")
    effective_to: datetime = Field(..., description="Assignment end date (UTC)")


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
