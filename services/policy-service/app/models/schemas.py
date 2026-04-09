"""Pydantic schemas for the PII Policy Module API."""
from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from app.utils.constants import ALLOWED_LANGUAGE_CODES, ALLOWED_MASK_TYPES


# ── Shared ────────────────────────────────────────────────────────────────────
class ErrorDetail(BaseModel):
    field: str
    issue: str

class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: Optional[List[ErrorDetail]] = None

class ErrorResponse(BaseModel):
    error: ErrorEnvelope

class Meta(BaseModel):
    total: int
    page: int
    limit: int


# ── PII Type ──────────────────────────────────────────────────────────────────
class PiiTypeCreate(BaseModel):
    pii_type_label: str
    regex_pattern: str
    example_values: List[str] = Field(..., min_length=3)
    mask_format: str   # full | partial | redact

    @field_validator("mask_format")
    @classmethod
    def _validate_mask_format(cls, v: str) -> str:
        v_norm = (v or "").strip().lower()
        if v_norm not in ALLOWED_MASK_TYPES:
            allowed = ", ".join(ALLOWED_MASK_TYPES)
            raise ValueError(f"Unsupported mask_format '{v_norm}'. Allowed: {allowed}")
        return v_norm

class PiiTypeUpdate(BaseModel):
    pii_type_label: Optional[str] = None
    regex_pattern: Optional[str] = None
    mask_format: Optional[str] = None

    @field_validator("mask_format")
    @classmethod
    def _validate_mask_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_norm = (v or "").strip().lower()
        if v_norm not in ALLOWED_MASK_TYPES:
            allowed = ", ".join(ALLOWED_MASK_TYPES)
            raise ValueError(f"Unsupported mask_format '{v_norm}'. Allowed: {allowed}")
        return v_norm

class PiiTypeOut(BaseModel):
    id: UUID = Field(alias="pii_type_id")
    pii_type_label: str
    regex_pattern: str
    mask_format: str
    created_at: datetime
    model_config = {"from_attributes": True, "populate_by_name": True}

class PiiTypeListResponse(BaseModel):
    data: List[PiiTypeOut]
    meta: Meta


# ── Policy ────────────────────────────────────────────────────────────────────
class PolicyPiiTypeLink(BaseModel):
    pii_type_id: UUID

class PolicyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_global: bool = False
    supported_languages: List[str]
    tenant_id: Optional[str] = None
    pii_types: Optional[List[PolicyPiiTypeLink]] = None

    @field_validator("supported_languages")
    @classmethod
    def _validate_supported_languages(cls, v: List[str]) -> List[str]:
        normed = [(x or "").strip().lower() for x in v or []]
        invalid = [x for x in normed if x not in ALLOWED_LANGUAGE_CODES]
        if invalid:
            allowed = ", ".join(ALLOWED_LANGUAGE_CODES)
            raise ValueError(f"Unsupported language codes {invalid}. Allowed: {allowed}")
        return normed

class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    supported_languages: Optional[List[str]] = None
    is_global: Optional[bool] = None
    tenant_id: Optional[str] = None
    pii_types: Optional[List[PolicyPiiTypeLink]] = None

class PolicyStatusUpdate(BaseModel):
    is_active: bool

class PolicyPiiTypeOut(BaseModel):
    pii_type_id: UUID
    pii_type_label: str
    mask_format: str
    model_config = {"from_attributes": True}

class PolicyOut(BaseModel):
    policy_id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool
    is_global: bool
    supported_languages: List[str]
    # New: full assignment set (empty for global policies).
    tenant_ids: List[str] = []
    pii_types_count: Optional[int] = None
    pii_types: List[PolicyPiiTypeOut] = []
    created_at: datetime
    model_config = {"from_attributes": True}

class PolicyDetailOut(BaseModel):
    policy_id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool
    is_global: bool
    supported_languages: List[str]
    tenant_ids: List[str] = []
    pii_types: List[PolicyPiiTypeOut] = []
    created_at: datetime
    model_config = {"from_attributes": True}

class PolicyListResponse(BaseModel):
    data: List[PolicyOut]
    meta: Meta


# ── Tenant Policy ─────────────────────────────────────────────────────────────
class TenantPolicyAssign(BaseModel):
    policy_id: UUID

class TenantPolicyOut(BaseModel):
    id: UUID
    tenant_id: str
    policy_id: UUID
    assigned_at: datetime
    model_config = {"from_attributes": True}

class TenantPolicyListResponse(BaseModel):
    data: List[PolicyOut]
    meta: Meta


# ── Audit Logs ────────────────────────────────────────────────────────────────
class AuditLogOut(BaseModel):
    id: UUID = Field(alias="pii_audit_id")
    trace_id: Optional[str] = None
    tenant_id: Optional[str] = None
    policy_id: Optional[UUID] = None
    target_context: Optional[str] = None
    pii_count: Optional[int] = None
    processing_ms: Optional[int] = None
    created_at: datetime
    model_config = {"from_attributes": True, "populate_by_name": True}

class AuditLogDetailOut(AuditLogOut):
    trace_json: Optional[Any] = None

class AuditLogListResponse(BaseModel):
    data: List[AuditLogOut]
    meta: Meta
