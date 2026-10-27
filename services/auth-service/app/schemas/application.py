"""
Application request/response schemas.

Field set follows the PRD (Onboard and Manage Applications / Edit Application):
Name, Description, Domain, Budget on create; Name, Description, Domain
editable, Budget excluded, on update. ``description`` is a later addition to
the ``applications`` table (migration a170c093332e) — the original API
contract predates it and didn't include it.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator

from app.models.application import ApplicationStatus
from app.schemas.base import BaseSchema
from app.schemas.common import SuccessResponse

# Matches applications.allocated_percentage — Numeric(5, 2): 0.00–100.00
_MAX_PERCENTAGE = Decimal("100")


_APPLICATION_CREATE_EXAMPLE = {
    "name": "Customer Portal",
    "description": "Public-facing translation widget for the customer portal",
    "domain": "portal.example.com",
    "allocated_percentage": 50.00,
    "service_fallbacks": {"nmt-service-a": ["nmt-service-b"]},
}


def normalize_service_fallbacks(v: Optional[Dict[str, List[str]]]) -> Optional[Dict[str, List[str]]]:
    """Shape checks for ``service_fallbacks`` that need no catalogue lookup.

    Ids are stripped, entries with an empty list are dropped (empty means "no
    fallback", same as a missing key), and a list may not repeat an id or name
    its own primary. Whether each id exists, is published, is in the tenant's
    Tier and shares the primary's task type is checked against the core DB in
    service_fallback_validator.
    """
    if v is None:
        return None
    out: Dict[str, List[str]] = {}
    for primary, fallbacks in v.items():
        primary = (primary or "").strip()
        if not primary:
            raise ValueError("service id keys must not be blank")
        cleaned = [(f or "").strip() for f in fallbacks]
        if any(not f for f in cleaned):
            raise ValueError(f"fallbacks of '{primary}' must not contain blank ids")
        if primary in cleaned:
            raise ValueError(f"'{primary}' cannot be its own fallback")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError(f"fallbacks of '{primary}' must not repeat a service")
        if cleaned:
            out[primary] = cleaned
    return out


class ApplicationCreate(BaseSchema):
    """POST body.

    ``extra="forbid"`` — same reasoning as ApplicationUpdate: a client sending
    e.g. ``allocated_budget`` (there is no such create field; only
    allocated_percentage) or a mistyped key would otherwise have it silently
    ignored, with the request still returning 201 — the client could
    reasonably believe the value took effect.
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [_APPLICATION_CREATE_EXAMPLE]})

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    domain: Optional[str] = Field(None, max_length=255)
    allocated_percentage: Optional[Decimal] = Field(None, ge=0, le=_MAX_PERCENTAGE)
    service_fallbacks: Optional[Dict[str, List[str]]] = None

    @field_validator("service_fallbacks", mode="after")
    @classmethod
    def _check_service_fallbacks(cls, v):
        return normalize_service_fallbacks(v)

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

    @field_validator("domain", "description", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
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


_APPLICATION_UPDATE_EXAMPLE = {
    "name": "Customer Portal",
    "description": "Updated description for the customer portal integration",
    "domain": "portal.example.com",
    "status": "ACTIVE",
    "policy_id": [1, 2],
    "service_fallbacks": {"nmt-service-a": ["nmt-service-b"]},
}


class ApplicationUpdate(BaseSchema):
    """PATCH body: name / domain / status only.

    ``extra="forbid"`` is what turns a client-sent ``allocated_percentage`` or
    ``allocated_budget`` into a 422 (contract: "allocation field sent —
    REJECTED, not silently dropped") without hand-rolled field detection —
    Pydantic raises on the unknown key before the handler ever sees it.
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [_APPLICATION_UPDATE_EXAMPLE]})

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    domain: Optional[str] = Field(None, max_length=255)
    status: Optional[ApplicationStatus] = None
    policy_id: Optional[List[int]] = None
    # Replaces the whole map; {} clears it. Omit to leave it unchanged.
    service_fallbacks: Optional[Dict[str, List[str]]] = None

    @field_validator("service_fallbacks", mode="after")
    @classmethod
    def _check_service_fallbacks(cls, v):
        # Same reasoning as name/status: omitted never reaches here, so None
        # means an explicit null — send {} to clear instead.
        if v is None:
            raise ValueError("must not be null; send {} to clear")
        return normalize_service_fallbacks(v)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("name", mode="after")
    @classmethod
    def _name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        # ``Optional[str] = None`` only means "may be omitted" — an omitted
        # field never reaches this validator (Pydantic skips validating an
        # unset default), so rejecting None here only fires when the client
        # sends an explicit "name": null, which name/status can't accept
        # (NOT NULL columns) the way domain/description legitimately can.
        if v is None:
            raise ValueError("must not be null")
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("status", mode="after")
    @classmethod
    def _status_not_null(cls, v: Optional[ApplicationStatus]) -> Optional[ApplicationStatus]:
        if v is None:
            raise ValueError("must not be null")
        return v

    @field_validator("domain", "description", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
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
    description: Optional[str] = None
    domain: Optional[str] = None
    allocated_percentage: Optional[Decimal] = None
    allocated_budget: Optional[Decimal] = None
    status: ApplicationStatus
    policy_id: Optional[List[int]] = None
    service_fallbacks: Dict[str, List[str]] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("service_fallbacks", mode="before")
    @classmethod
    def _null_fallbacks_to_empty(cls, v):
        return v or {}


class ApplicationListItem(BaseSchema):
    """One row in GET (list) — contract's list item omits tenant_id/created_at."""

    id: int
    name: str
    description: Optional[str] = None
    domain: Optional[str] = None
    allocated_percentage: Optional[Decimal] = None
    allocated_budget: Optional[Decimal] = None
    status: ApplicationStatus
    policy_id: Optional[List[int]] = None
    service_fallbacks: Dict[str, List[str]] = Field(default_factory=dict)

    @field_validator("service_fallbacks", mode="before")
    @classmethod
    def _null_fallbacks_to_empty(cls, v):
        return v or {}


class ApplicationListData(BaseSchema):
    """Payload of GET /tenants/{tenant_id}/applications — nested under
    ``data`` like every other list endpoint's payload (e.g. ListTenantsResponse)."""

    items: list[ApplicationListItem]
    total: int


class CreateApplicationResponse(SuccessResponse):
    """POST /tenants/{tenant_id}/applications"""

    data: ApplicationResponse


class GetApplicationResponse(SuccessResponse):
    """GET /tenants/{tenant_id}/applications/{application_id}"""

    data: ApplicationResponse


class ListApplicationsResponse(SuccessResponse):
    """GET /tenants/{tenant_id}/applications"""

    data: ApplicationListData


class UpdateApplicationResponse(SuccessResponse):
    """PATCH /tenants/{tenant_id}/applications/{application_id}"""

    data: ApplicationResponse
