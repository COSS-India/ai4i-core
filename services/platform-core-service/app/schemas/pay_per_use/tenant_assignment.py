from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TierAssignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to assign the tier to")
    tier_id: str = Field(..., description="UUID of the PPU tier to assign")
    budget: Decimal = Field(..., ge=0, max_digits=15, decimal_places=4, description="Budget limit in INR (paise precision)")
    effective_from: datetime = Field(..., description="Assignment start date (UTC)")
    effective_to: datetime = Field(..., description="Assignment end date (UTC)")


class TierReassignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to reassign")
    tier_id: str = Field(..., description="UUID of the new PPU tier to assign")


class TopUpRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to top up")
    amount: Decimal = Field(..., gt=0, max_digits=15, decimal_places=4, description="Amount to add in INR")


class TopUpResponse(BaseModel):
    tenant_id: str
    added: Decimal
    available_balance: Decimal


class ReviseBudgetRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant whose budget is being revised")
    budget: Decimal = Field(..., ge=0, max_digits=15, decimal_places=4, description="New budget limit in INR, replacing the current budget_limit")


class ReviseBudgetResponse(BaseModel):
    tenant_id: str
    budget_limit: Decimal
    available_balance: Decimal
    updated_at: datetime


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
