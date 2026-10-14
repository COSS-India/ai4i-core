"""Internal endpoints — service-to-service calls, not exposed to end users."""

import logging
import secrets
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis


from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.dependencies.services import ServiceService, get_service_service
from app.models.policy_management.audit_log import PolicyAuditLog
from app.repositories.policy_management.policy_repository import PolicyRepository
from app.services.pay_per_use import tier_service
from app.services.policy_management.policy_cache import (
    GLOBAL_POLICY_IDS_KEY,
    cache_policy,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Internal"])


@router.post("/ppu/billing-cycle-reset",include_in_schema=False)
async def billing_cycle_reset(session: AsyncSession = Depends(get_db)):
    """Promote pending_monthly_quota → monthly_quota for all tier quotas.
    Called by the monthly cron on the 1st of each month, before quota-reset on auth-service.
    """
    updated = await tier_service.apply_pending_quotas(session)
    return {"message": "Billing cycle reset complete", "quotas_updated": updated}


async def _require_internal_caller(
    x_internal_service_token: str = Header(default=""),
) -> None:
    """Gate for endpoints on this router that return credentials unmasked —
    defense in depth beyond "not exposed through APISIX", since a
    network-boundary mistake alone shouldn't be enough to leak a plaintext
    secret. inference-service sends the same value as
    MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN.
    """
    expected = settings.internal_service_shared_secret or ""
    if not expected or not secrets.compare_digest(
        x_internal_service_token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


class _AuditLogCreate(BaseModel):
    policy_id: Optional[List[int]] = None
    trace_id: Optional[str] = None
    model_request: Optional[Dict[str, Any]] = None
    response: Optional[Dict[str, Any]] = None
    guardrail_info: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None


@router.post("/policy-audit-logs", include_in_schema=False)
async def create_policy_audit_log(
    body: _AuditLogCreate,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Write a policy guardrail audit log entry. Called by inference-service
    after each LLM request where a PII policy was applied."""
    log = PolicyAuditLog(
        policy_id=body.policy_id,
        trace_id=body.trace_id,
        model_request=body.model_request,
        response=body.response,
        guardrail_info=body.guardrail_info,
        created_by=body.created_by,
    )
    session.add(log)
    await session.commit()
    return {"id": log.id}


@router.get(
    "/services/{service_id:path}",
    include_in_schema=False,
    dependencies=[Depends(_require_internal_caller)],
)
async def internal_get_service(
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
):
    """Full, unmasked service record for inference-service's own
    resolution use — never the response the public GET /services/{id} sends,
    which always masks credentials regardless of caller identity (see
    serializers.mask_service_secrets).

    Also restores Triton's Authorization header: inference-service used to
    resolve services via the public route with no identity headers, which
    the RBAC filter always treats as non-admin and strips api_key from.
    """
    data = await svc.get_service_detail(service_id)
    return {"success": True, "data": data}


class UsageReportRunRequest(BaseModel):
    """``frequency`` comes from the pyjob job's env (USAGE_REPORT_FREQUENCY);
    omitted → monthly."""

    frequency: Optional[str] = None


@router.post(
    "/usage-report/run",
    include_in_schema=False,
    dependencies=[Depends(_require_internal_caller)],
)
async def usage_report_run(request: Request, body: UsageReportRunRequest = UsageReportRunRequest()):
    """One scheduled run of the Usage Viewer report (AI4IDS-3278), triggered
    once per period by the pyjob `usage_report` CronJob: emails the latest
    complete period to every Usage Viewer and logs each send in the app logs.
    Not idempotent in this release (no send log): every call sends again —
    see app.services.usage_report.scheduler."""
    from app.services.usage_report.scheduler import run_scheduled_report

    try:
        result = await run_scheduled_report(body.frequency, request.app.state.http_client)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return result.as_dict()


@router.get(
    "/policies/global",
    include_in_schema=False,
    dependencies=[Depends(_require_internal_caller)],
)
async def internal_get_global_policies(
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> Dict[str, Any]:
    """Return IDs of all active global policies and re-warm the Redis index.
    Called by inference-service on a cache miss for the global policy index."""
    repo = PolicyRepository(session)
    policies = await repo.get_global_active()
    policy_ids = [p.id for p in policies]
    try:
        await redis.delete(GLOBAL_POLICY_IDS_KEY)
        if policy_ids:
            await redis.sadd(GLOBAL_POLICY_IDS_KEY, *policy_ids)
    except Exception:
        logger.warning("Failed to re-warm global policy index")
    return {"success": True, "data": policy_ids}


@router.get(
    "/policies/{policy_id}",
    include_in_schema=False,
    dependencies=[Depends(_require_internal_caller)],
)
async def internal_get_policy(
    policy_id: int,
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> Dict[str, Any]:
    """Fetch a policy by id, re-warm the Redis cache, and return the cached
    payload. Called by inference-service on a cache miss so the guardrail
    never goes dark after the TTL expires."""
    repo = PolicyRepository(session)
    policy = await repo.get_by_id(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    data = await cache_policy(policy, session, redis)
    if data is None:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to cache policy {policy_id}; unable to serve guardrail data",
        )
    return {"success": True, "data": data}
