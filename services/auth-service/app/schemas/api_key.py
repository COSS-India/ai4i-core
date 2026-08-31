"""
API key request/response schemas.

Ownership: an API key belongs to an Application, not a User (migration
e9f0a1b2c3d4 dropped api_key.user_id in favor of api_key.application_id).
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import ConfigDict, Field, model_validator

from app.schemas.base import BaseSchema
from app.schemas.common import MessageData, SuccessResponse


# ── Requests ──

class CreateAPIKeyRequest(BaseSchema):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Stable permission names (e.g. nmt.inference). At least one "
            "permission is required — an API key with no permissions cannot "
            "authorize any request and would only be confusing to the caller."
        ),
    )
    expires_days: Optional[int] = Field(None, ge=1, description="Key lifetime in days; defaults to API_KEY_EXPIRE_DAYS")
    application_id: int = Field(..., description="Application this key is issued under.")
    allocated_percentage: Optional[Decimal] = Field(
        None,
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
        description="Share of the Application's allocated_budget reserved for this key, as a percentage.",
    )
    budget: Optional[Decimal] = Field(
        None,
        gt=0,
        max_digits=15,
        decimal_places=2,
        description=(
            "₹ ceiling for this key, as an alternative to allocated_percentage. The server "
            "derives an equivalent allocated_percentage of the Application's own Budget "
            "immediately to run the same ALLOCATION_TOTAL_EXCEEDED cap check every "
            "allocated_percentage-created key goes through, but stores this exact requested "
            "amount as allocated_budget — the two can therefore round differently by a "
            "fraction of a percent. This exact amount is a create-time snapshot only: the "
            "first later reallocation that cascades into this key (PUT /auth/allocations) "
            "re-derives allocated_budget from allocated_percentage instead, which can move "
            "the ceiling slightly away from what was originally requested here. Give at "
            "most one of allocated_percentage / budget."
        ),
    )

    @model_validator(mode="after")
    def _check_at_most_one_allocation_field(self) -> "CreateAPIKeyRequest":
        if self.allocated_percentage is not None and self.budget is not None:
            raise ValueError("Give at most one of allocated_percentage or budget, not both.")
        return self


class UpdateAPIKeyRequest(BaseSchema):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="forbid",
    )

    key_name: Optional[str] = Field(None, min_length=1, max_length=100)
    permissions: Optional[list[str]] = Field(
        None,
        min_length=1,
        description=(
            "Omit to leave permissions unchanged. If supplied, must contain at "
            "least one permission name — an explicit empty list is rejected (same "
            "as create) since a zero-permission key can't authorize anything."
        ),
    )
    expires_days: Optional[int] = Field(None, ge=1)


# ── Response payloads (the ``data`` field) ──

class CreateAPIKeyData(BaseSchema):
    id: int
    api_key: str = Field(..., description="32-char hex key. Store securely — shown only once.")
    key_name: str
    permissions: list[str]
    expires_at: Optional[datetime] = None
    application_id: int
    allocated_percentage: Optional[Decimal] = None
    allocated_budget: Optional[Decimal] = Field(
        None,
        description=(
            "The requested ₹ ceiling verbatim (rounded to cents) when this key was "
            "created via `budget`; otherwise derived as application.allocated_budget * "
            "allocated_percentage / 100. Not a standing invariant either way — the next "
            "reallocation that cascades into this key re-derives it from "
            "allocated_percentage, which can move it away from an originally-exact "
            "`budget` value."
        ),
    )


class APIKeyItem(BaseSchema):
    """Masked API key as returned on list and update."""

    id: int
    key_name: str
    api_key: str = Field(
        ...,
        description="Masked key (first 4 and last 4 characters). The raw key is never returned after create.",
    )
    allocated_percentage: Optional[Decimal] = None
    allocated_budget: Optional[Decimal] = None
    permissions: list[str]
    expires_at: Optional[datetime] = None
    is_active: bool
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ApplicationAPIKeysGroup(BaseSchema):
    """One Application and the keys issued under it — GET /auth/api-keys groups by Application."""

    application_id: int
    api_keys: list[APIKeyItem]


class APIKeyAdminItem(BaseSchema):
    """GET /auth/api-keys/all item — flat (not grouped by application), with
    the current budget position pulled from platform-core's per-key usage
    ledger. No owner PII: there is no user_id FK to join through any more."""

    id: int
    key_name: str
    api_key: str = Field(
        ...,
        description="Masked key (first 4 and last 4 characters). The raw key is never returned after create.",
    )
    application_id: int
    allocated_percentage: Optional[Decimal] = None
    allocated_budget: Optional[Decimal] = None
    budget_used: Optional[Decimal] = Field(
        None, description="Cumulative spend against this key, from platform-core's budget_usage ledger."
    )
    budget_pending: Optional[Decimal] = Field(
        None, description="allocated_budget minus budget_used; None if allocated_budget is unset."
    )
    permissions: list[str]
    expires_at: Optional[datetime] = None
    is_active: bool
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Route responses: inherit SuccessResponse and override ``data`` ──

class CreateAPIKeyResponse(SuccessResponse):
    """POST /auth/api-keys"""

    data: CreateAPIKeyData


class ListAPIKeysResponse(SuccessResponse):
    """GET /auth/api-keys — one entry per Application, each with its keys."""

    data: list[ApplicationAPIKeysGroup]


class UpdateAPIKeyResponse(SuccessResponse):
    """PATCH /auth/api-keys/{key_id}"""

    data: APIKeyItem


class RevokeAPIKeyResponse(SuccessResponse):
    """DELETE /auth/api-keys/{key_id}"""

    data: MessageData


class ListAllAPIKeysResponse(SuccessResponse):
    """GET /auth/api-keys/all"""

    data: list[APIKeyAdminItem]


class ValidateAPIKeyResponse(BaseSchema):
    valid: bool = True
    application_id: Optional[str] = None
    permission_ids: list[int] = []
    token_type: str = "api_key"


class ValidateAPIKeyErrorResponse(BaseSchema):
    valid: bool = False
    error: str
    message: str
