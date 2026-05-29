"""Schemas for PII admin endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Domain management ──────────────────────────────────────────────────────

class NewDomainRequest(BaseModel):
    domain_id:   str = Field(..., max_length=50)
    description: str


class DeployRequest(BaseModel):
    domain_id: str
    rules:     List[Dict[str, Any]]


class BulkActivateRequest(BaseModel):
    domain_ids: List[str]


# ── Tenant → domain mapping ────────────────────────────────────────────────

class TenantDomainUpsertRequest(BaseModel):
    tenant_id: str
    domain_id: str


class TenantDomainDeleteRequest(BaseModel):
    tenant_id: str


class TenantDomainEntry(BaseModel):
    tenant_id:  str
    domain_id:  str
    updated_at: Optional[datetime] = None


# ── Regex generation ───────────────────────────────────────────────────────

class GenerateRegexRequest(BaseModel):
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
