"""Internal endpoints — service-to-service calls, not exposed to end users."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.exceptions import EntityNotFoundError
from app.dependencies.services import get_api_key_service, get_quota_notification_service, get_tenant_service
from app.schemas.quota import QuotaLimitUpdatedRequest
from app.services.api_key_service import APIKeyService
from app.services.quota_notification_service import QuotaNotificationService
from app.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Internal"])


@router.get("/tenant-plan/tenant-id/{tenant_id}")
async def get_tenant_plan(tenant_id: str, svc: TenantService = Depends(get_tenant_service)):
    try:
        tid = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id")
    try:
        return await svc.get_tenant_plan(tid)
    except EntityNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No plan found for tenant")


class BudgetExhaustedRequest(BaseModel):
    exhausted: bool


class QuotaExhaustedRequest(BaseModel):
    inference_name: str


@router.post("/ppu/api-key/{api_key_id}/budget-exhausted", status_code=status.HTTP_204_NO_CONTENT)
async def set_api_key_budget_exhausted(
    api_key_id: str,
    body: BudgetExhaustedRequest,
    svc: APIKeyService = Depends(get_api_key_service),
):
    """Scoped to one API Key, not a tenant — budget is tracked per key
    (budget_usage), so one key hitting its own ceiling must not block every
    other key under the same tenant. Replaces the old
    /ppu/tenant/{tenant_id}/budget-exhausted (removed — it flagged every key
    under a tenant from a single key's own usage)."""
    try:
        kid = int(api_key_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid api_key_id")
    await svc.set_budget_exhausted_for_key(kid, body.exhausted)


@router.post("/ppu/tenant/{tenant_id}/budget-exhausted", status_code=status.HTTP_204_NO_CONTENT)
async def set_budget_exhausted_deprecated_tenant_scoped(tenant_id: str, body: BudgetExhaustedRequest):
    """DEPRECATED — kept only so a rolling deploy doesn't 404 an
    old-code kafka-consumers instance still posting here. auth-service and
    kafka-consumers deploy separately; _notify_auth treats a 404 as
    permanent (no retry), so removing this in the same commit that
    introduces /ppu/api-key/{id}/budget-exhausted would silently drop every
    exhaustion flag raised during whichever side of the rollout lands
    first.

    Deliberately a no-op, not a restoration of the old tenant-wide
    fan-out (git history has that if it's ever genuinely needed again):
    fanning out from here would reintroduce exactly the bug
    /ppu/api-key/{id}/budget-exhausted exists to fix — one Key's own usage
    blocking every sibling Key under the same tenant. A flag missed during
    the rollout window self-heals on that Key's own next billed request
    once kafka-consumers is deployed onto the new per-key path.

    Remove once kafka-consumers is confirmed running the version that
    posts to /ppu/api-key/{id}/budget-exhausted instead of this path.
    """
    try:
        int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id")
    logger.warning(
        "Deprecated /ppu/tenant/%s/budget-exhausted hit (exhausted=%s) — "
        "kafka-consumers is still posting the old tenant-scoped path; "
        "no-op until it's redeployed onto /ppu/api-key/{id}/budget-exhausted.",
        tenant_id, body.exhausted,
    )


@router.post("/ppu/tenant/{tenant_id}/quota-exhausted", status_code=status.HTTP_204_NO_CONTENT)
async def set_quota_exhausted(
    tenant_id: str,
    body: QuotaExhaustedRequest,
    svc: APIKeyService = Depends(get_api_key_service),
):
    try:
        tid = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id")
    await svc.set_quota_exhausted_for_tenant(tid, body.inference_name)


@router.post("/ppu/quota-reset", status_code=status.HTTP_204_NO_CONTENT,include_in_schema=False)
async def reset_monthly_quota(svc: APIKeyService = Depends(get_api_key_service)):
    """HDEL all quota-* fields from every active tenant API key hash.
    Called by the monthly cron on the 1st of each month.
    """
    await svc.reset_all_quota_fields()


@router.post("/ppu/tenant/{tenant_id}/quota-reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_tenant_quota(
    tenant_id: str,
    svc: APIKeyService = Depends(get_api_key_service),
):
    """HDEL all quota-* fields from this tenant's active API key hashes.
    Called after a tier reassignment, since ppu_quota_usage starts fresh
    under the new tier_id and any quota-exhausted flag set under the
    previous tier would otherwise stay stuck until the monthly cron.
    """
    try:
        tid = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id")
    await svc.clear_quota_flags_for_tenant(tid)


@router.post("/ppu/tier/quota-limit-updated", status_code=status.HTTP_204_NO_CONTENT)
async def notify_quota_limit_updated(
    body: QuotaLimitUpdatedRequest,
    background_tasks: BackgroundTasks,
    svc: QuotaNotificationService = Depends(get_quota_notification_service),
):
    await svc.notify_quota_limit_updated(
        body.tier_name, body.tenant_ids, background_tasks, tier_id=body.tier_id
    )


@router.get("/tenants/tier/{tier_id}/count")
async def get_tenant_count_for_tier(
    tier_id: str,
    svc: TenantService = Depends(get_tenant_service),
) -> dict:
    """Backs platform-core-service's delete_tier "is this tier assigned to
    any tenant" check — tenant<->tier assignment lives solely on
    tenants.tier_id now that ppu_tenant_tier_assignments is dropped, so
    platform-core-service (which owns the tier itself, not the assignment)
    has to ask auth-service rather than querying its own DB."""
    return {"count": await svc.tenant_count_for_tier(tier_id)}
