"""Internal endpoints — service-to-service calls, not exposed to end users."""
from decimal import Decimal

from ai4i_core.exceptions import ValidationError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.exceptions import EntityNotFoundError
from app.dependencies.services import get_api_key_service, get_ppu_notification_service, get_tenant_service
from app.repositories.platform_core_db_repositories.ppu_tenant_tier_assignments_repository import \
    PpuTenantTierAssignmentsRepository
from app.schemas.ppu import QuotaLimitUpdatedRequest
from app.services.api_key_service import APIKeyService
from app.services.ppu_notification_service import PPUNotificationService
from app.services.tenant_service import TenantService

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


@router.post("/ppu/tenant/{tenant_id}/budget-exhausted", status_code=status.HTTP_204_NO_CONTENT)
async def set_budget_exhausted(
    tenant_id: str,
    body: BudgetExhaustedRequest,
    svc: APIKeyService = Depends(get_api_key_service),
):
    """kafka-consumers triggers this after a billing event; the actual exhausted
    determination is re-derived here from the DB rather than trusted from the body."""
    try:
        tid = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id")
    try:
        _, available_balance = await PpuTenantTierAssignmentsRepository.get_active_tier_and_balance(
            tenant_id)
    except ValidationError:  # Tenant has no active tier assignment.
        available_balance = Decimal("0")
    await svc.set_budget_exhausted_for_tenant(tid, available_balance <= 0)


@router.post("/ppu/tenant/{tenant_id}/quota-exhausted", status_code=status.HTTP_204_NO_CONTENT)
async def set_quota_exhausted(
    tenant_id: str,
    body: QuotaExhaustedRequest,
    svc: APIKeyService = Depends(get_api_key_service),
):
    """kafka-consumers tells us which inference_name it thinks just tipped over; the
    actual exhausted determination is re-derived here from the DB rather than trusted
    from the body.
    This is to preserve consistency since we have left the atomicity after checking in kafka consumer.
    If there is a discrepancy found in Kafka's call and the db (source of truth) and quota exhausted for the service
    is false, then it will do nothing.
    else it will call set_quota_exhasted_for_tenant for the tenant and the service
    """
    try:
        tid = int(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id")

    try:
        tier_id, _ = await PpuTenantTierAssignmentsRepository.get_active_tier_and_balance(tenant_id)
        quota_exhausted_map = await PpuTenantTierAssignmentsRepository.get_quota_exhausted_map(
            tenant_id, tier_id)
    except ValidationError:
        quota_exhausted_map = {}

    if quota_exhausted_map.get(body.inference_name) is False:
        return
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
    svc: PPUNotificationService = Depends(get_ppu_notification_service),
):
    await svc.notify_quota_limit_updated(body.tier_name, body.tenant_ids, background_tasks)
