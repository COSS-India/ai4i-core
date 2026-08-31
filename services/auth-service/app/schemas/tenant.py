"""
Tenant request/response schemas.
"""

import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional, Union
from uuid import UUID

from pydantic import AliasChoices, EmailStr, Field, StrictBool, field_serializer, field_validator, model_validator

from app.models.user import CreationType
from app.schemas.base import BaseSchema
from app.schemas.common import MessageData, SuccessResponse
from app.schemas.text_validators import check_name_chars as _check_name_chars
from app.schemas.text_validators import clean_text as _clean_text
from app.models.tenant import TenantStatus
from app.core.constants import RoleName

# E.164 phone: + followed by 2–15 digits
_E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")

# Formatting chars commonly added to phone numbers by users or stored systems
_PHONE_FORMAT_RE = re.compile(r"[ \-()\.]")

# Punctuation allowed in organisation names beyond letters/digits
_ORG_PUNCT = frozenset(" -.'/&(),")


def _check_org_chars(v: str) -> str:
    """Validate organisation name character set.

    Allows Unicode letters, combining marks, decimal digits, and common
    business punctuation. Requires at least one letter or digit so
    punctuation-only values (e.g. '--') are rejected.
    """
    has_alnum = False
    for c in v:
        cat = unicodedata.category(c)
        if cat.startswith(("L", "M")) or cat == "Nd":
            has_alnum = True
        elif c not in _ORG_PUNCT:
            raise ValueError(
                "may only contain letters, digits, spaces, hyphens, dots, "
                "apostrophes, ampersands, parentheses, forward slashes, and commas"
            )
    if not has_alnum:
        raise ValueError("must contain at least one letter or digit")
    return v


def _normalize_phone(v: Any, *, validate_e164: bool) -> Optional[str]:
    """Strip common phone formatting chars; coerce blank to None.

    With validate_e164=True (create paths) the result must match E.164.
    With validate_e164=False (update paths) stored numbers that pre-date
    the E.164 constraint are accepted as-is after formatting is stripped.
    """
    if v is None:
        return None
    if not isinstance(v, str):
        return v
    v = _PHONE_FORMAT_RE.sub("", v.strip())
    if not v:
        return None
    if validate_e164 and not _E164_RE.match(v):
        raise ValueError("must be in E.164 format (e.g. +919876543210)")
    return v


class TenantUserRole(str, Enum):
    """Roles assignable to users provisioned under a tenant."""

    USER = RoleName.USER.value
    TENANT_ADMIN = RoleName.TENANT_ADMIN.value
    USAGE_VIEWER = RoleName.USAGE_VIEWER.value
    MODERATOR = RoleName.MODERATOR.value



class TenantCreate(BaseSchema):
    contact_name: str = Field(..., min_length=2, max_length=80)
    organisation: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone_number: Optional[str] = None
    plan_id: Optional[UUID] = None
    tier_id: Optional[UUID] = None
    # No ge=0 here: a negative value must surface as the contract's named
    # 422 INVALID_BUDGET (checked in TenantService.create_tenant), not a
    # generic Pydantic field-constraint error.
    allocated_budget: Optional[Decimal] = Field(
        None, max_digits=15, decimal_places=2, description="Initial budget, INR."
    )
    budget_effective_from: Optional[datetime] = None
    budget_effective_to: Optional[datetime] = None

    @field_validator("organisation", "contact_name", mode="before")
    @classmethod
    def _clean(cls, v: Any) -> Any:
        return _clean_text(v)

    @field_validator("organisation", mode="after")
    @classmethod
    def _validate_org(cls, v: str) -> str:
        return _check_org_chars(v)

    @field_validator("contact_name", mode="after")
    @classmethod
    def _validate_contact_name(cls, v: str) -> str:
        return _check_name_chars(v)

    @field_validator("phone_number", mode="before")
    @classmethod
    def _normalize_phone(cls, v: Any) -> Optional[str]:
        return _normalize_phone(v, validate_e164=True)


class TenantUpdate(BaseSchema):
    # max_length matches DB column (255) so existing stored values round-trip safely
    contact_name: Optional[str] = Field(None, min_length=2, max_length=255)
    organisation: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    status: Optional[TenantStatus] = None

    @field_validator("organisation", "contact_name", mode="before")
    @classmethod
    def _clean(cls, v: Any) -> Any:
        return _clean_text(v)

    @field_validator("organisation", mode="after")
    @classmethod
    def _validate_org(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _check_org_chars(v)
        return v

    @field_validator("contact_name", mode="after")
    @classmethod
    def _validate_contact_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _check_name_chars(v)
        return v

    @field_validator("phone_number", mode="before")
    @classmethod
    def _normalize_phone(cls, v: Any) -> Optional[str]:
        # No strict E.164 check: existing stored numbers pre-date this constraint
        return _normalize_phone(v, validate_e164=False)


class TenantStatusUpdate(BaseSchema):
    status: TenantStatus


class TenantResponse(BaseSchema):
    tenant_id: int = Field(validation_alias="id")
    contact_name: str = Field(validation_alias="name")
    organisation: str
    email: str
    phone_number: Optional[str] = None
    status: TenantStatus

    @field_serializer("status")
    def _status_as_api_value(self, value: Union[TenantStatus, str]) -> str:
        if isinstance(value, TenantStatus):
            return value.value
        return str(value).strip().upper()

    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None
    tier_id: Optional[UUID] = None
    allocated_budget: Optional[Decimal] = None
    budget_effective_from: Optional[datetime] = None
    budget_effective_to: Optional[datetime] = None


class TenantUserCreate(BaseSchema):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=80)
    phone_number: Optional[str] = None
    role: TenantUserRole = TenantUserRole.USER

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_full_name(cls, v: Any) -> Any:
        return _clean_text(v)

    @field_validator("full_name", mode="after")
    @classmethod
    def _validate_full_name(cls, v: str) -> str:
        return _check_name_chars(v)

    @field_validator("phone_number", mode="before")
    @classmethod
    def _normalize_phone(cls, v: Any) -> Optional[str]:
        return _normalize_phone(v, validate_e164=True)


class TenantUserCreateResponse(BaseSchema):
    user_id: str
    setup_token: str
    message: str = "Tenant user provisioned. Share the setup link to complete onboarding."


class TenantUserStatusUpdate(BaseSchema):
    # is_tenant_active is intentionally NOT accepted here: it is managed by the
    # tenant status API (PATCH /tenants/{id}/status → SUSPENDED/DEACTIVATED/ACTIVE).
    is_active: Optional[StrictBool] = None


class TenantUserUpdate(BaseSchema):
    email: Optional[EmailStr] = None
    # max_length matches DB column (255) so existing stored values round-trip safely
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone_number: Optional[str] = None
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    role: Optional[TenantUserRole] = None

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_full_name(cls, v: Any) -> Any:
        return _clean_text(v)

    @field_validator("full_name", mode="after")
    @classmethod
    def _validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _check_name_chars(v)
        return v

    @field_validator("phone_number", mode="before")
    @classmethod
    def _normalize_phone(cls, v: Any) -> Optional[str]:
        # No strict E.164 check: existing stored numbers pre-date this constraint
        return _normalize_phone(v, validate_e164=False)

    @model_validator(mode='after')
    def at_least_one_field(self) -> 'TenantUserUpdate':
        if not any([self.email, self.full_name, self.phone_number, self.username, self.role is not None]):
            raise ValueError("Provide at least one field to update.")
        return self


class TenantUserResponse(BaseSchema):
    """Tenant-scoped user list/detail item including assignable role."""

    # ORM exposes ``id``; API responses use ``user_id`` (field name).
    user_id: UUID = Field(validation_alias=AliasChoices("id", "user_id"))
    username: str
    email: str
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    # Tenant-lock flag: cleared (False) for every user while the tenant is
    # SUSPENDED/DEACTIVATED and restored (True) on reactivation. The user's own
    # ``is_active`` is never touched by tenant lifecycle changes, so the frontend
    # combines both flags to render the effective status.
    is_tenant_active: Optional[bool] = None
    # True once the user has completed setup (a credentials row exists). Lets the
    # frontend tell an admin-suspended user (activated, is_active=False) apart
    # from one who never set a password (Pending Activation).
    is_activated: Optional[bool] = None
    creation_type: Optional[CreationType] = None
    roles: list[str]


class TenantPlanData(BaseSchema):
    tenant_id: str
    tenant_name: str
    plan_id: str
    plan_name: Optional[str] = None
    tier: Optional[str] = None
    plan_cost: Optional[float] = None
    quota_config: dict[str, Any] = Field(default_factory=dict)
    rate_limit_config: dict[str, Any] = Field(default_factory=dict)
    allowed_services: list[Any] = Field(default_factory=list)


class DeleteTenantUserData(BaseSchema):
    user_id: str
    deleted: bool


# ── Tier / budget ──

class TenantTierAssignRequest(BaseSchema):
    # Deliberately str, not UUID: an invalid format must surface as the
    # contract's named 400 (checked in TenantService.assign_tenant_tier),
    # not FastAPI's automatic 422 for a failed UUID field parse.
    tier_id: str


class TenantTierAssignData(BaseSchema):
    tenant_id: int
    tier_id: UUID
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None


class TenantBudgetRequest(BaseSchema):
    action: Literal["top-up", "top-down"]
    amount: Decimal = Field(..., gt=0, max_digits=15, decimal_places=2)


class TenantBudgetData(BaseSchema):
    """Unwrapped — no success/data envelope. Matches the endpoint this
    replaces (platform-core-service's PATCH /pay-per-use/tenant/budget)."""

    tenant_id: int
    allocated_budget: Optional[Decimal] = None
    applications_recomputed: Optional[int] = Field(
        None, description="Not computed in this release; always null."
    )
    keys_recomputed: Optional[int] = Field(
        None, description="Not computed in this release; always null."
    )
    updated_at: Optional[datetime] = None


class TenantTierListItem(BaseSchema):
    tenant_id: int
    tenant_name: str
    tier_id: UUID
    tier_name: Optional[str] = None
    allocated_budget: Optional[Decimal] = None
    budget_effective_from: Optional[datetime] = None
    budget_effective_to: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateTenantResponse(SuccessResponse):
    """POST /auth/tenants"""

    data: TenantResponse


class ListTenantsResponse(SuccessResponse):
    """GET /auth/tenants"""

    data: list[TenantResponse]


class GetTenantResponse(SuccessResponse):
    """GET /auth/tenants/{tenant_id}"""

    data: TenantResponse


class UpdateTenantResponse(SuccessResponse):
    """PATCH /auth/tenants/{tenant_id}"""

    data: TenantResponse


class UpdateTenantStatusResponse(SuccessResponse):
    """PATCH /auth/tenants/{tenant_id}/status"""

    data: TenantResponse


class GetTenantPlanResponse(SuccessResponse):
    """GET /auth/tenants/{tenant_id}/plan"""

    data: TenantPlanData


class ListTenantUsersResponse(SuccessResponse):
    """GET /auth/tenants/{tenant_id}/users"""

    data: list[TenantUserResponse]


class CreateTenantUserResponse(SuccessResponse):
    """POST /auth/tenants/{tenant_id}/users"""

    data: TenantUserCreateResponse


class UpdateTenantUserStatusResponse(SuccessResponse):
    """PATCH /auth/tenants/{tenant_id}/users/{user_id}/status"""

    data: TenantUserResponse


class ResendTenantUserSetupLinkResponse(SuccessResponse):
    """POST /auth/tenants/{tenant_id}/users/{user_id}/resend-setup-link"""

    data: MessageData


class UpdateTenantUserResponse(SuccessResponse):
    """PATCH /auth/tenants/{tenant_id}/users/{user_id}"""

    data: TenantUserResponse


class DeleteTenantUserResponse(SuccessResponse):
    """DELETE /auth/tenants/{tenant_id}/users/{user_id}"""

    data: DeleteTenantUserData


class TenantTierAssignResponse(SuccessResponse):
    """PATCH /auth/tenants/{tenant_id}/tier"""

    data: TenantTierAssignData


class ListTenantTiersResponse(SuccessResponse):
    """GET /auth/tenants/tier/list"""

    data: list[TenantTierListItem]
