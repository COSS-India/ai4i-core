from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Pydantic embeds the raw Decimal bound (e.g. ctx={"ge": Decimal("0")}) in the
# error context for gt/ge/lt/le constraint failures on a Decimal field. The
# platform's global RequestValidationError handler (ai4i_core) only sanitizes
# Exception instances in ctx, not Decimal, so JSONResponse crashes with an
# unhandled 500 instead of returning 422. Enforcing the bound via a
# field_validator instead produces a plain ValueError, which that handler
# already stringifies correctly — so validate manually rather than via
# Field(ge=...)/Field(gt=...) for any Decimal field here.


class TierAssignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to assign the tier to")
    tier_id: str = Field(..., description="UUID of the PPU tier to assign")
    budget: Decimal = Field(..., max_digits=15, decimal_places=4, description="Budget limit in INR (paise precision)")
    effective_from: datetime = Field(..., description="Assignment start date (UTC)")
    effective_to: datetime = Field(..., description="Assignment end date (UTC)")

    @field_validator("budget")
    @classmethod
    def _budget_must_be_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("budget must be greater than or equal to 0")
        return v


class TierReassignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to reassign")
    tier_id: str = Field(..., description="UUID of the new PPU tier to assign")


class TopUpRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to top up")
    amount: Decimal = Field(..., max_digits=15, decimal_places=4, description="Amount to add in INR")

    @field_validator("amount")
    @classmethod
    def _amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        return v


class TopUpResponse(BaseModel):
    tenant_id: str
    added: Decimal
    available_balance: Decimal


class ReviseBudgetRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant whose budget is being revised")
    action: Literal["top-up", "top-down"] = Field(..., description="Whether to increase (top-up) or decrease (top-down) the current budget by amount")
    amount: Decimal = Field(..., max_digits=15, decimal_places=4, description="Amount in INR to add (top-up) or subtract (top-down) from the current budget_limit")

    @field_validator("amount")
    @classmethod
    def _amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        return v


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
