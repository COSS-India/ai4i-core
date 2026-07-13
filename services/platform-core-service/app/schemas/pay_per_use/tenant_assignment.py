from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

# Pydantic embeds the raw Decimal bound (e.g. ctx={"ge": Decimal("0")}) in the
# error context for gt/ge/lt/le constraint failures on a Decimal field. The
# platform's global RequestValidationError handler (ai4i_core) only sanitizes
# Exception instances in ctx, not Decimal, so JSONResponse crashes with an
# unhandled 500 instead of returning 422. Enforcing the bound via an
# AfterValidator instead produces a plain ValueError, which that handler
# already stringifies correctly — so validate manually rather than via
# Field(ge=...)/Field(gt=...) for any Decimal field here.


def _reject_negative(v: Decimal) -> Decimal:
    if v < 0:
        raise ValueError("must be greater than or equal to 0")
    return v


def _reject_non_positive(v: Decimal) -> Decimal:
    if v <= 0:
        raise ValueError("must be greater than 0")
    return v


NonNegativeDecimal = Annotated[Decimal, AfterValidator(_reject_negative)]
PositiveDecimal = Annotated[Decimal, AfterValidator(_reject_non_positive)]


class TierAssignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to assign the tier to")
    tier_id: str = Field(..., description="UUID of the PPU tier to assign")
    budget: NonNegativeDecimal = Field(..., max_digits=15, decimal_places=4, description="Budget limit in INR (paise precision)")
    effective_from: datetime = Field(..., description="Assignment start date (UTC)")
    effective_to: datetime = Field(..., description="Assignment end date (UTC)")


class TierReassignRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant to reassign")
    tier_id: str = Field(..., description="UUID of the new PPU tier to assign")


class ReviseBudgetRequest(BaseModel):
    tenant_id: str = Field(..., description="ID of the tenant whose budget is being revised")
    action: Literal["top-up", "top-down"] = Field(..., description="Whether to increase (top-up) or decrease (top-down) the current budget by amount")
    amount: PositiveDecimal = Field(..., max_digits=15, decimal_places=4, description="Amount in INR to add (top-up) or subtract (top-down) from the current budget_limit")


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
