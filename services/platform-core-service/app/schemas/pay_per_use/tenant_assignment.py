from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Pydantic v2 embeds the raw Decimal bound (e.g. ctx={"ge": Decimal("0")}) in
# the error context for gt/ge/lt/le constraint failures on a Decimal field.
# ai4i_core's RequestValidationError handler now sanitizes any non-JSON-safe
# value in ctx generically (not just Exception instances), so plain
# Field(ge=...)/Field(gt=...) constraints are safe to use directly here —
# they also keep the "minimum"/"exclusiveMinimum" constraint visible in the
# OpenAPI schema, unlike enforcing the bound via a validator.


class TierAssignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to assign the tier to")
    tier_id: str = Field(..., description="UUID of the PPU tier to assign")
    budget: Decimal = Field(..., gt=0, max_digits=15, decimal_places=8, description="Budget limit in INR (paise precision)")
    effective_from: datetime = Field(..., description="Assignment start date (UTC)")
    effective_to: datetime = Field(..., description="Assignment end date (UTC)")

    @model_validator(mode="after")
    def check_effective_dates_not_same(self) -> "TierAssignRequest":
        if self.effective_from.date() == self.effective_to.date():
            raise ValueError("Effective From and Effective To cannot be the same date.")
        return self


class TierReassignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to reassign")
    tier_id: str = Field(..., description="UUID of the new PPU tier to assign")


class ReviseBudgetRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant whose budget is being revised")
    action: Literal["top-up", "top-down"] = Field(..., description="Whether to increase (top-up) or decrease (top-down) the current budget by amount")
    amount: Decimal = Field(..., gt=0, max_digits=15, decimal_places=8, description="Amount in INR to add (top-up) or subtract (top-down) from the current budget_limit")


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
