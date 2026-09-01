"""
Budget Allocation APIs — three level-specific endpoints, replacing the old
single PUT /auth/allocations (scoped by a tenant_id/application_id query
param). Each is a thin wrapper over the same shared allocation_validator
algorithm — see AllocationService and allocation-reallocation-flow.md
Section 4.4 for the full picture.

The wire shape for "what value to set" is one discriminated object
everywhere (AllocationValue: {type: PERCENTAGE|FIXED, value}), replacing
the old pair of mutually-exclusive optional fields
(allocated_percentage/allocated_budget). PERCENTAGE maps to
allocated_percentage, FIXED to allocated_budget — same two underlying
values allocation_validator.convert() already produces, just a different
wire encoding. A response row's own `type` reports "FIXED" only for a row
that was JUST submitted as FIXED in the SAME request — it is not a
persisted, sticky attribute; an unlisted/re-fit/unchanged row always
reports back "PERCENTAGE" (see allocation_service._response_allocation).
"""

from decimal import Decimal
from typing import Literal, Optional

from pydantic import ConfigDict, Field, model_validator

from app.schemas.base import BaseSchema

AllocationType = Literal["PERCENTAGE", "FIXED"]

_PCT_MAX_DIGITS = 5
_AMT_MAX_DIGITS = 15
_DECIMAL_PLACES = 2


def _digit_count(value: Decimal) -> int:
    return len(value.as_tuple().digits)


def _decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


# ── Request ──────────────────────────────────────────────────────────────


class AllocationValue(BaseSchema):
    """{type, value} — the one shape every allocation row uses, request and
    response alike. Bounds/precision depend on ``type``: PERCENTAGE is
    0-100 with the same NUMERIC(5,2) precision as applications.
    allocated_percentage/api_key.allocated_percentage; FIXED is a
    non-negative amount with the same NUMERIC(15,2) precision as the
    allocated_budget columns. Checked here (cheap, request-shape only) —
    the real, transaction-scoped conversion still happens server-side in
    allocation_validator.convert(), same as before."""

    model_config = ConfigDict(extra="forbid")

    type: AllocationType
    value: Decimal = Field(..., ge=0)

    @model_validator(mode="after")
    def _check_bounds_and_precision(self) -> "AllocationValue":
        if _decimal_places(self.value) > _DECIMAL_PLACES:
            raise ValueError(f"value must have at most {_DECIMAL_PLACES} decimal places.")
        if self.type == "PERCENTAGE":
            if self.value > Decimal("100"):
                raise ValueError("PERCENTAGE value must be between 0 and 100.")
            if _digit_count(self.value) > _PCT_MAX_DIGITS:
                raise ValueError(f"PERCENTAGE value must have at most {_PCT_MAX_DIGITS} digits.")
        else:
            if _digit_count(self.value) > _AMT_MAX_DIGITS:
                raise ValueError(f"FIXED value must have at most {_AMT_MAX_DIGITS} digits.")
        return self


class APIKeyAllocationRow(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    api_key_id: int
    allocation: AllocationValue


class ApplicationAllocationRow(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    application_id: int
    allocation: AllocationValue
    api_keys: list[APIKeyAllocationRow] = Field(default_factory=list)


_TENANT_BUDGET_ALLOCATION_REQUEST_EXAMPLE = {
    "applications": [
        {
            "application_id": "<place your id here>",
            "allocation": {"type": "PERCENTAGE", "value": 60.00},
        },
        {
            "application_id": "<place your id here>",
            "allocation": {"type": "PERCENTAGE", "value": 40.00},
        },
    ],
}


class TenantBudgetAllocationRequest(BaseSchema):
    """PUT /auth/tenants/{tenant_id}/budget-allocation.

    An Application under the tenant NOT listed here is not required to be
    — it's proportionally re-fit against what's left of the Tenant's
    (unchanged) total, the same unconditional re-fit rule used at every
    other edge where a parent's children are being resolved."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [_TENANT_BUDGET_ALLOCATION_REQUEST_EXAMPLE]},
    )

    applications: list[ApplicationAllocationRow] = Field(..., min_length=1)


class ApplicationBudgetAllocationRequest(BaseSchema):
    """PUT /auth/applications/{application_id}/budget-allocation.

    ``allocation`` is the Application's own current value — required by
    the wire shape, but this endpoint never changes it (that only happens
    via the Tenant-level endpoint); it must match what's already stored,
    or the call is rejected (APPLICATION_ALLOCATION_MISMATCH) rather than
    silently ignored. ``api_keys`` not listed here are left exactly as
    they are — the Application's own total isn't changing in this call,
    so nothing forces an untouched Key to react."""

    model_config = ConfigDict(extra="forbid")

    application_id: int
    allocation: AllocationValue
    api_keys: list[APIKeyAllocationRow] = Field(default_factory=list)


class APIKeyBudgetAllocationRequest(BaseSchema):
    """PUT /auth/api-keys/{key_id}/budget-allocation.

    ``api_key_id`` must match the path's ``{key_id}`` — carried in the body
    too only because the contract specifies it, not because it's needed
    (KEY_ID_MISMATCH if they disagree)."""

    model_config = ConfigDict(extra="forbid")

    api_key_id: int
    allocation: AllocationValue


# ── Response ─────────────────────────────────────────────────────────────


class APIKeyAllocationResponseItem(BaseSchema):
    api_key_id: int
    allocation: AllocationValue
    allocated_budget: Decimal


class ApplicationAllocationResponseItem(BaseSchema):
    """The one response shape shared by all three endpoints — a bare array
    of these for the Tenant-level call, a single one for the other two.

    ``api_keys`` is ``None`` when this Application's own Keys were not
    resolved this call (the Tenant-level endpoint only cascades into an
    Application's Keys when that Application's own amount changed or the
    caller nested explicit api_keys under it — see
    AllocationService.update_tenant_application_allocations) — distinct
    from ``[]``, which means the Keys WERE resolved and this Application
    genuinely has none. The Application-level and single-Key endpoints
    always resolve every Key under the Application, so this is only ever
    ``None`` on a Tenant-level response row."""

    application_id: int
    allocation: AllocationValue
    allocated_budget: Decimal
    api_keys: Optional[list[APIKeyAllocationResponseItem]] = None
