"""Schemas for domain policy read endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, RootModel


class DomainListResponse(RootModel):
    """GET /pii/domains

    A ``RootModel`` rather than a field-wrapping class: the frontend
    (``piiService.ts``) validates this as a bare JSON array of domain ids,
    not an object, so the wire response must stay exactly ``["...", "..."]``.
    This only gives it a real named schema in Swagger's components list
    instead of an anonymous inline array type — the JSON body is unchanged.
    """

    root: List[str]


class PolicyRule(BaseModel):
    entity_type:  str
    # detection_service.py/_apply_redactions default to "REDACT" when a stored
    # rule omits this key (rule.get("action", "REDACT")) — matched here so a
    # rule written before "action" was always sent still reads back cleanly.
    action:       str = "REDACT"        # REDACT | REDACT_TAG | MASK
    config:       Dict[str, Any] = {}
    custom_regex: Optional[str] = None


class PolicyMeta(BaseModel):
    version:     str
    description: str


class PolicyResponse(BaseModel):
    """GET /pii/policy/{domain}

    ``meta``/``rules`` are optional because the route returns a bare ``{}``
    for an unknown domain (``PolicySyncService.get_policy`` returns ``None``
    on a cache miss) rather than a 404 — this is a public, unauthenticated
    endpoint, so that miss is an expected, not exceptional, response.
    """

    meta:  Optional[PolicyMeta] = None
    rules: List[PolicyRule] = Field(default_factory=list)


class DomainSummary(BaseModel):
    domain_id:   str
    is_active:   bool
    description: Optional[str] = None
