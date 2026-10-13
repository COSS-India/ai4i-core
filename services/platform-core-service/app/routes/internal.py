"""Internal endpoints — service-to-service calls, not exposed to end users."""

import logging
import secrets
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.services import ServiceService, get_service_service
from app.models.policy_management.audit_log import PolicyAuditLog
from app.services.pay_per_use import tier_service

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
