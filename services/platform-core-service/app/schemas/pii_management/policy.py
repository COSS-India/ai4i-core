"""Schemas for domain policy read endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PolicyRule(BaseModel):
    entity_type:  str
    action:       str                    # REDACT | REDACT_TAG | MASK
    config:       Dict[str, Any] = {}
    custom_regex: Optional[str] = None


class PolicyMeta(BaseModel):
    version:     str
    description: str


class PolicyResponse(BaseModel):
    meta:  PolicyMeta
    rules: List[PolicyRule]


class DomainSummary(BaseModel):
    domain_id:   str
    is_active:   bool
    description: Optional[str] = None
