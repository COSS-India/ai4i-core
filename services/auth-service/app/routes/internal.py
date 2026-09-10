"""Internal endpoints — service-to-service calls, not exposed to end users."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import EntityNotFoundError
from app.dependencies.services import get_api_key_service, get_quota_notification_service, get_tenant_service
from app.schemas.quota import QuotaLimitUpdatedRequest, TierReactivatedRequest
from app.services.api_key_service import APIKeyService
from app.services.quota_notification_service import QuotaNotificationService
from app.services.tenant_service import TenantService
from app.services.tier_status_cache import tier_status_cache

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
    model_config = ConfigDict(json_schema_extra={"examples": [{"exhausted": True}]})

    exhausted: bool


class QuotaExhaustedRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"inference_name": "nmt"}]})

    inference_name: str


@router.post("/ppu/api-key/{api_key_id}/budget-exhausted", status_code=status.HTTP_204_NO_CONTENT)
async def set_api_key_budget_exhausted(
    api_key_id: str,
    body: BudgetExhaustedRequest,
    svc: APIKeyService = Depends(get_api_key_service),
):
    """Scoped to one API Key, not a tenant — budget is tracked per key
    (budget_usage), so one key hitting its own ceiling must not block every
    other key under the same tenant. Is the Kafka billing consumer's
    intended notification target going forward — see
    set_budget_exhausted_deprecated_tenant_scoped below for the old
    /ppu/tenant/{tenant_id}/budget-exhausted path this replaces, kept
    temporarily so a rolling deploy doesn't drop the signal entirely.
    set_budget_exhausted_for_tenant (the tenant-wide fan-out) is also still
    used directly by TenantService for a budget revision's own recompute."""
    try:
        kid = int(api_key_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid api_key_id")
    await svc.set_budget_exhausted_for_key(kid, body.exhausted)


@router.post("/ppu/tenant/{tenant_id}/budget-exhausted", status_code=status.HTTP_204_NO_CONTENT)
async def set_budget_exhausted_deprecated_tenant_scoped(
    tenant_id: str,
    body: BudgetExhaustedRequest,
    svc: APIKeyService = Depends(get_api_key_service),
):
    """DEPRECATED — thin compat alias, kept only so a rolling deploy doesn't
    404 an old-code kafka-consumers instance still posting here instead of
    /ppu/api-key/{id}/budget-exhausted. auth-service and kafka-consumers
    deploy separately, and _notify_auth treats any non-5xx/429 response
    (a 404 from a deleted route included) as permanent — no retry — so
    removing this route outright would silently drop every exhaustion
    signal an old-code consumer sends during that window, with no recovery
    until the tenant's next billed request happens to re-trigger it.

    Deliberately falls back to the OLD tenant-wide fan-out
    (set_budget_exhausted_for_tenant) rather than being a no-op: the old
    consumer's payload has no api_key_id to route to a specific key with
    anyway, so a temporary, imprecise flag (blocks every key under the
    tenant, not just the one that actually crossed its own ceiling — the
    exact bug set_budget_exhausted_for_key exists to fix) is still real
    enforcement for the rollout window, which a silent no-op would not be.

    Remove once kafka-consumers is confirmed running the version that
    posts to /ppu/api-key/{id}/budget-exhausted instead of this path.
    """
    try:
        tid = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id")
    logger.warning(
        "Deprecated /ppu/tenant/%s/budget-exhausted hit (exhausted=%s) — kafka-consumers is "
        "still posting the old tenant-scoped path; falling back to the tenant-wide fan-out "
        "until it's redeployed onto /ppu/api-key/{id}/budget-exhausted.",
        tenant_id, body.exhausted,
    )
    await svc.set_budget_exhausted_for_tenant(tid, body.exhausted)


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
    await svc.notify_quota_limit_updated(body.tier_name, body.tenant_ids, background_tasks)


@router.post("/ppu/tier/reactivated", status_code=status.HTTP_204_NO_CONTENT)
async def notify_tier_reactivated(
    body: TierReactivatedRequest,
    svc: APIKeyService = Depends(get_api_key_service),
):
    """Update status cache and clear quota-* exhaustion flags for the reactivated tier.

    Called by platform-core-service after a DEACTIVATED → ACTIVE transition so
    that auth-service stops issuing 403s immediately and tenants don't keep
    receiving 429s from stale quota-exhausted flags set before the tier was paused.
    """
    tier_status_cache.set_status(body.tier_id, "ACTIVE")
    for tenant_id in body.tenant_ids:
        await svc.clear_quota_flags_for_tenant(tenant_id)


class TierDeactivatedRequest(BaseModel):
    tier_id: str = Field(..., description="UUID of the deactivated tier.")


@router.post("/ppu/tier/deactivated", status_code=status.HTTP_204_NO_CONTENT)
async def notify_tier_deactivated(body: TierDeactivatedRequest):
    """Immediately reflect a tier deactivation in the local status cache.

    Called by platform-core-service after an ACTIVE → DEACTIVATED transition.
    Without this push, auth-service would continue issuing 200s for up to
    tier_status_cache_refresh_interval_seconds before the periodic reload picks
    up the new status. The periodic reload remains as a backstop.
    """
    tier_status_cache.set_status(body.tier_id, "DEACTIVATED")
