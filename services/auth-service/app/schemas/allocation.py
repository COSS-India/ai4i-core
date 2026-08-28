"""
PUT /auth/allocations — request/response schemas.

One endpoint, scoped by exactly one of two mutually-exclusive query params
(?tenant_id= for Institution->Applications, ?application_id= for
Application->API Keys — see AllocationService/routes/allocations.py);
request/response array names mirror each other (application_allocations /
api_key_allocations), with no separate "scope" discriminator field, since
which array is populated already says which scope answered the call.
"""

from decimal import Decimal
from typing import Optional

from pydantic import ConfigDict, Field, model_validator

from app.schemas.base import BaseSchema
from app.schemas.common import SuccessResponse

# ── Request ──────────────────────────────────────────────────────────────


def _exactly_one_of_percentage_or_amount(percentage, amount, *, row_label: str):
    """Shared request-shape check for both row types — NOT the same thing as
    allocation_validator.convert's own check (that one runs server-side,
    inside the transaction, against the actual parent amount; this one is a
    cheap request-shape rejection before any DB work happens at all)."""
    if (percentage is None) == (amount is None):
        raise ValueError(
            f"{row_label}: exactly one of allocated_percentage or allocated_budget is required."
        )


class APIKeyAllocationInput(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    api_key_id: int
    allocated_percentage: Optional[Decimal] = Field(None, ge=0, max_digits=5, decimal_places=2)
    allocated_budget: Optional[Decimal] = Field(None, ge=0, max_digits=15, decimal_places=2)

    @model_validator(mode="after")
    def _check_exactly_one(self) -> "APIKeyAllocationInput":
        _exactly_one_of_percentage_or_amount(
            self.allocated_percentage, self.allocated_budget,
            row_label=f"api_key_id={self.api_key_id}",
        )
        return self


class ApplicationAllocationInput(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    application_id: int
    allocated_percentage: Optional[Decimal] = Field(None, ge=0, max_digits=5, decimal_places=2)
    allocated_budget: Optional[Decimal] = Field(None, ge=0, max_digits=15, decimal_places=2)
    api_key_allocations: Optional[list[APIKeyAllocationInput]] = Field(
        None,
        description=(
            "Explicit edits to THIS Application's own Keys, resolved in the same "
            "transaction. Any Key under it NOT listed here is proportionally "
            "re-fit against what's left of its new budget — never left untouched, "
            "unlike a sibling Application this call doesn't mention."
        ),
    )

    @model_validator(mode="after")
    def _check_exactly_one(self) -> "ApplicationAllocationInput":
        _exactly_one_of_percentage_or_amount(
            self.allocated_percentage, self.allocated_budget,
            row_label=f"application_id={self.application_id}",
        )
        return self


_ALLOCATION_UPDATE_REQUEST_EXAMPLE = {
    "application_allocations": [
        {"application_id": "<place your id here>", "allocated_percentage": 60.00},
        {"application_id": "<place your id here>", "allocated_percentage": 40.00},
    ],
}


class AllocationUpdateRequest(BaseSchema):
    """Body shape is the same regardless of scope; which of the two fields is
    populated must match the ?tenant_id=/?application_id= query param — that
    cross-check needs the query param, so it happens in AllocationService,
    not here (a body-only validator can't see the query string)."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": _ALLOCATION_UPDATE_REQUEST_EXAMPLE})

    application_allocations: Optional[list[ApplicationAllocationInput]] = None
    api_key_allocations: Optional[list[APIKeyAllocationInput]] = None


# ── Response ─────────────────────────────────────────────────────────────


class ResolvedAPIKeyAllocation(BaseSchema):
    api_key_id: int
    allocated_percentage: Decimal
    allocated_budget: Decimal
    auto_refitted: bool = Field(
        description="True for a Key the caller never listed but the unconditional re-fit rule touched anyway."
    )


class ResolvedApplicationAllocation(BaseSchema):
    application_id: int
    allocated_percentage: Decimal
    allocated_budget: Decimal
    api_key_allocations: Optional[list[ResolvedAPIKeyAllocation]] = Field(
        None,
        description=(
            "Every Key under this Application that has one — present only when this "
            "Application's own amount changed or the caller explicitly edited its Keys; "
            "absent when this row's Keys were never in scope for this call."
        ),
    )


class AllocationUpdateData(BaseSchema):
    parent_id: str = Field(description="The tenant_id or application_id that scoped this call.")
    total_allocated_percentage: Decimal = Field(
        description=(
            "Live sum across EVERY child at this level (a fresh read, not derived "
            "from the rows below) — unrelated to which rows this call touched."
        )
    )
    application_allocations: Optional[list[ResolvedApplicationAllocation]] = Field(
        None, description="Populated for the tenant_id-scoped call; absent for application_id-scoped."
    )
    api_key_allocations: Optional[list[ResolvedAPIKeyAllocation]] = Field(
        None, description="Populated for the application_id-scoped call; absent for tenant_id-scoped."
    )


class AllocationUpdateResponse(SuccessResponse):
    """PUT /auth/allocations"""

    data: AllocationUpdateData
