"""
PII guard endpoints.

All auth and RBAC is handled by APISIX upstream (see api_permissions.json).
This file contains zero auth logic — routes trust the request is pre-authorized.

Public  (no permission required):
    GET  /api/v1/pii/domains
    GET  /api/v1/pii/policy/{domain}

Permissioned (APISIX enforces):
    POST /api/v1/pii/redact                      (perm 90 — pii_guard.inference)
    GET  /api/v1/pii/admin/all-domains            (perm 91 — pii_guard.admin)
    POST /api/v1/pii/admin/domain                (perm 91)
    POST /api/v1/pii/admin/deploy                (perm 91)
    POST /api/v1/pii/admin/activate-domains      (perm 91)
    POST /api/v1/pii/admin/generate-regex        (perm 91)
    GET  /api/v1/pii/admin/tenant-domains        (perm 91)
    POST /api/v1/pii/admin/tenant-domain         (perm 91)
    POST /api/v1/pii/admin/tenant-domain/delete  (perm 91)
    GET  /api/v1/pii/admin/audit-logs            (perm 92 — pii_guard.audit.read)
"""

from __future__ import annotations

import importlib
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pii_database import get_pii_db, _pii_session_factory
from app.core.config import settings
from app.repositories.pii_management.audit_log_repository import AuditLogRepository
from app.repositories.pii_management.policy_repository import PolicyRepository
from app.repositories.pii_management.tenant_map_repository import TenantMapRepository
from app.schemas.pii_management.admin import (
    AuditLogEntry,
    BulkActivateRequest,
    DeployRequest,
    GenerateRegexRequest,
    GenerateRegexResponse,
    NewDomainRequest,
    TenantDomainDeleteRequest,
    TenantDomainEntry,
    TenantDomainUpsertRequest,
)
from app.schemas.pii_management.policy import DomainSummary
from app.schemas.pii_management.redaction import RedactionRequest, RedactionResponse

logger = logging.getLogger(__name__)

# ── Service accessors (singletons stored on app.state at startup) ──────────

def _get_policy_sync(request: Request):
    return request.app.state.pii_policy_sync


def _get_redaction_service(request: Request):
    return request.app.state.pii_redaction_service


# ── Routers ────────────────────────────────────────────────────────────────

_public_router = APIRouter(tags=["PII"])
_redact_router = APIRouter(tags=["PII"])
_admin_router  = APIRouter(prefix="/admin", tags=["PII Admin"])

# Module-level router that __init__.py includes into v1_router.
router = APIRouter(prefix="/pii")


# ── Public endpoints ───────────────────────────────────────────────────────

@_public_router.get("/domains", response_model=List[str])
async def get_domains(policy_sync=Depends(_get_policy_sync)):
    """List active PII domains."""
    return policy_sync.list_active_domains()


@_public_router.get("/policy/{domain}")
async def get_policy(domain: str, policy_sync=Depends(_get_policy_sync)):
    """Return the policy JSON for a domain."""
    return policy_sync.get_policy(domain) or {}


# ── Redact endpoint ────────────────────────────────────────────────────────

@_redact_router.post("/redact", response_model=RedactionResponse)
async def redact_text(
    request_body: RedactionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    include_original_text: bool = Query(default=False),
    x_target:    str            = Header("user",  alias="X-Target"),
    x_language:  str            = Header("en",    alias="X-Language"),
    x_tenant_id: Optional[str] = Header(None,    alias="X-Tenant-Id"),
):
    """
    Detect and redact PII in the supplied text.

    Headers
    -------
    X-Tenant-Id   : tenant identifier (injected by APISIX from the validated JWT)
    X-Language    : language code — en | hi | mr | ta  (default: en)
    X-Target      : caller context — "user" = lenient scoring, anything else = strict
    """
    redaction_svc = _get_redaction_service(request)

    # Tenant ID comes from the APISIX-injected header; no token cross-check needed.
    tenant_id = (x_tenant_id or "").strip() or None

    return await redaction_svc.redact(
        text=request_body.text,
        tenant_id=tenant_id,
        language=x_language,
        target=x_target,
        include_original=include_original_text,
        background_tasks=background_tasks,
    )


# ── Admin endpoints ────────────────────────────────────────────────────────

@_admin_router.get("/all-domains", response_model=List[DomainSummary])
async def get_all_domains(db: AsyncSession = Depends(get_pii_db)):
    repo = PolicyRepository(db)
    rows = await repo.get_all()
    return [
        DomainSummary(
            domain_id=row.domain_id,
            is_active=row.is_active or False,
            description=(
                row.policy_json.get("meta", {}).get("description")
                if isinstance(row.policy_json, dict) else None
            ),
        )
        for row in rows
    ]


@_admin_router.post("/domain", status_code=201)
async def create_domain(
    req: NewDomainRequest,
    db: AsyncSession = Depends(get_pii_db),
):
    repo = PolicyRepository(db)
    existing = await repo.get_by_id(req.domain_id)
    if existing:
        raise HTTPException(409, f"Domain '{req.domain_id}' already exists.")
    await repo.create(req.domain_id, req.description)
    return {"status": "success"}


@_admin_router.post("/deploy")
async def deploy(
    req: DeployRequest,
    request: Request,
    db: AsyncSession = Depends(get_pii_db),
):
    repo = PolicyRepository(db)
    updated = await repo.update_rules(req.domain_id, req.rules)
    if not updated:
        raise HTTPException(404, "Domain not found.")
    # Signal policy cache refresh via Redis pub/sub
    redis = getattr(request.app.state, "redis_client", None)
    if redis:
        await redis.publish("policy_updates", "deployed")
    return {"status": "saved"}


@_admin_router.post("/activate-domains")
async def activate_domains(
    req: BulkActivateRequest,
    request: Request,
    db: AsyncSession = Depends(get_pii_db),
):
    repo = PolicyRepository(db)
    await repo.set_active_bulk(req.domain_ids)
    redis = getattr(request.app.state, "redis_client", None)
    if redis:
        await redis.publish("policy_updates", "activated")
    return {"status": "success"}


@_admin_router.post("/generate-regex", response_model=GenerateRegexResponse)
async def generate_regex(req: GenerateRegexRequest):
    """
    Use the platform LLM service to generate a regex from an example string.
    """
    llm_url = settings.pii_llm_url
    prompt = (
        f"Generate a general python regex pattern to EXTRACT data similar to this example: "
        f"'{req.example_text}'. Use word boundaries (\\b). Return only the raw regex string."
    )
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                llm_url,
                json={"query": prompt, "system_prompt": None, "context": None},
                timeout=20.0,
            )
            if resp.status_code == 200:
                return GenerateRegexResponse(regex=resp.json().get("result", "").strip('`"\'\n '))
            return GenerateRegexResponse(regex=f"HTTP_ERROR_{resp.status_code}")
        except Exception as exc:
            return GenerateRegexResponse(regex=f"LLM_ERROR: {exc}")


@_admin_router.get("/tenant-domains", response_model=List[TenantDomainEntry])
async def list_tenant_domain_mappings(db: AsyncSession = Depends(get_pii_db)):
    repo = TenantMapRepository(db)
    rows = await repo.get_all()
    return [TenantDomainEntry(tenant_id=r.tenant_id, domain_id=r.domain_id, updated_at=r.updated_at)
            for r in rows]


@_admin_router.post("/tenant-domain")
async def upsert_tenant_domain(
    req: TenantDomainUpsertRequest,
    request: Request,
    db: AsyncSession = Depends(get_pii_db),
):
    tid, did = req.tenant_id.strip(), req.domain_id.strip()
    if not tid or not did:
        raise HTTPException(400, "tenant_id and domain_id are required.")

    policy_repo = PolicyRepository(db)
    if not await policy_repo.get_by_id(did):
        raise HTTPException(404, f"domain_id '{did}' not found in domain_policies.")

    tenant_repo = TenantMapRepository(db)
    await tenant_repo.upsert(tid, did)

    redis = getattr(request.app.state, "redis_client", None)
    if redis:
        await redis.publish("policy_updates", "tenant_map")

    # Eagerly refresh the in-memory policy cache for this pod
    policy_sync = getattr(request.app.state, "pii_policy_sync", None)
    if policy_sync:
        async with _pii_session_factory() as fresh_db:
            await policy_sync.refresh(fresh_db)

    return {"status": "success", "tenant_id": tid, "domain_id": did}


@_admin_router.post("/tenant-domain/delete")
async def delete_tenant_domain(
    req: TenantDomainDeleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_pii_db),
):
    tid = req.tenant_id.strip()
    if not tid:
        raise HTTPException(400, "tenant_id is required.")

    repo = TenantMapRepository(db)
    await repo.delete(tid)

    redis = getattr(request.app.state, "redis_client", None)
    if redis:
        await redis.publish("policy_updates", "tenant_map")

    policy_sync = getattr(request.app.state, "pii_policy_sync", None)
    if policy_sync:
        async with _pii_session_factory() as fresh_db:
            await policy_sync.refresh(fresh_db)

    return {"status": "success"}


@_admin_router.get("/audit-logs", response_model=List[AuditLogEntry])
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_pii_db),
):
    repo = AuditLogRepository(db)
    rows = await repo.list_recent(limit)
    return [
        AuditLogEntry(
            id=r.id,
            trace_id=str(r.trace_id) if r.trace_id else None,
            tenant_id=r.tenant_id,
            domain_id=r.domain_id,
            target_context=r.target_context,
            pii_count=r.pii_count,
            processing_ms=r.processing_ms,
            trace_json=r.trace_json,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── Aggregate sub-routers into module router ───────────────────────────────

router.include_router(_public_router)
router.include_router(_redact_router)
router.include_router(_admin_router)
