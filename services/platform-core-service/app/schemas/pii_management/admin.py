"""Schemas for PII admin endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Simple acknowledgements ─────────────────────────────────────────────────

class StatusResponse(BaseModel):
    """Generic ``{"status": "..."}`` acknowledgement shared by the simple
    admin actions below (create domain, deploy rules, activate domains,
    delete a tenant-domain mapping) — their bodies are otherwise identical,
    so this is reused rather than one near-duplicate class per route."""

    status: str


# ── Domain management ──────────────────────────────────────────────────────

_NEW_DOMAIN_REQUEST_EXAMPLE = {
    "domain_id": "healthcare",
    "description": "PII redaction rules for healthcare-domain text (patient names, MRNs, diagnoses)",
}


class NewDomainRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _NEW_DOMAIN_REQUEST_EXAMPLE})

    domain_id:   str = Field(..., max_length=50)
    description: str


_DEPLOY_REQUEST_EXAMPLE = {
    "domain_id": "healthcare",
    "rules": [
        {
            "entity_type": "PATIENT_NAME",
            "pattern": r"\b[A-Z][a-z]+ [A-Z][a-z]+\b",
            "risk_score": 0.8,
        }
    ],
}


class DeployRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _DEPLOY_REQUEST_EXAMPLE})

    domain_id: str
    rules:     List[Dict[str, Any]]


_BULK_ACTIVATE_REQUEST_EXAMPLE = {
    "domain_ids": ["healthcare", "finance"],
}


class BulkActivateRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _BULK_ACTIVATE_REQUEST_EXAMPLE})

    domain_ids: List[str]


# ── Tenant → domain mapping ────────────────────────────────────────────────

_TENANT_DOMAIN_UPSERT_REQUEST_EXAMPLE = {
    "tenant_id": "tenant-001",
    "domain_id": "healthcare",
}


class TenantDomainUpsertRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _TENANT_DOMAIN_UPSERT_REQUEST_EXAMPLE})

    tenant_id: str
    domain_id: str


class TenantDomainUpsertResponse(BaseModel):
    """POST /pii/admin/tenant-domain"""

    status: str
    tenant_id: str
    domain_id: str


_TENANT_DOMAIN_DELETE_REQUEST_EXAMPLE = {
    "tenant_id": "tenant-001",
}


class TenantDomainDeleteRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _TENANT_DOMAIN_DELETE_REQUEST_EXAMPLE})

    tenant_id: str


class TenantDomainEntry(BaseModel):
    tenant_id:  str
    domain_id:  str
    updated_at: Optional[datetime] = None


# ── Regex generation ───────────────────────────────────────────────────────

_GENERATE_REGEX_REQUEST_EXAMPLE = {
    "example_text": "Patient ID: PT-2024-00123",
}


class GenerateRegexRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _GENERATE_REGEX_REQUEST_EXAMPLE})

    example_text: str


class GenerateRegexResponse(BaseModel):
    regex: str


# ── Audit logs ─────────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id:             int
    trace_id:       Optional[str]     = None
    tenant_id:      Optional[str]     = None
    domain_id:      Optional[str]     = None
    target_context: Optional[str]     = None
    pii_count:      Optional[int]     = None
    processing_ms:  Optional[int]     = None
    trace_json:     Optional[Any]     = None
    created_at:     Optional[datetime] = None
