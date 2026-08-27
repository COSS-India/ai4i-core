"""
Application request/response schemas.

Field set follows the API contract exactly (Onboard and Manage Applications):
Application has no ``description`` column today — the ``applications`` table
(migration e9f0a1b2c3d4) was built with id/tenant_id/name/domain/
allocated_percentage/allocated_budget/status/audit-quad only, and the contract's
request/response bodies mirror that. If Description needs to ship, it needs a
migration + model column first — out of scope here.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import ConfigDict, Field, field_validator

from app.models.application import ApplicationStatus
from app.schemas.base import BaseSchema

# Matches applications.allocated_percentage — Numeric(5, 2): 0.00–100.00
_MAX_PERCENTAGE = Decimal("100")


class ApplicationCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    allocated_percentage: Optional[Decimal] = Field(None, ge=0, le=_MAX_PERCENTAGE)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("name", mode="after")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("domain", mode="before")
    @classmethod
    def _blank_domain_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator("allocated_percentage", mode="after")
    @classmethod
    def _round_percentage(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is None:
            return None
        return v.quantize(Decimal("0.01"))


class ApplicationUpdate(BaseSchema):
    """PATCH body: name / domain / status only.

    ``extra="forbid"`` is what turns a client-sent ``allocated_percentage`` or
    ``allocated_budget`` into a 422 (contract: "allocation field sent —
    REJECTED, not silently dropped") without hand-rolled field detection —
    Pydantic raises on the unknown key before the handler ever sees it.
    """

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    status: Optional[ApplicationStatus] = None

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("name", mode="after")
    @classmethod
    def _name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("domain", mode="before")
    @classmethod
    def _blank_domain_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return v


class ApplicationResponse(BaseSchema):
    """GET one / POST response — full shape per contract."""

    id: int
    tenant_id: int
    name: str
    domain: Optional[str] = None
    allocated_percentage: Optional[Decimal] = None
    allocated_budget: Optional[Decimal] = None
    status: ApplicationStatus
    created_at: datetime


class ApplicationListItem(BaseSchema):
    """One row in GET (list) — contract's list item omits tenant_id/created_at."""

    id: int
    name: str
    domain: Optional[str] = None
    allocated_percentage: Optional[Decimal] = None
    allocated_budget: Optional[Decimal] = None
    status: ApplicationStatus


class ApplicationListResponse(BaseSchema):
    """GET /tenants/{tenant_id}/applications — unwrapped per contract."""

    items: list[ApplicationListItem]
    total: int
