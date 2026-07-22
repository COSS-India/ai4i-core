"""Internal endpoints — service-to-service calls, not exposed to end users."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.core.responses import success_response
from app.dependencies.services import ServiceService, get_service_service
from app.schemas.model_management.service import validate_service_id
from app.services.pay_per_use import tier_service

router = APIRouter(tags=["Internal"])


@router.post("/ppu/billing-cycle-reset",include_in_schema=False)
async def billing_cycle_reset(session: AsyncSession = Depends(get_db)):
    """Promote pending_monthly_quota → monthly_quota for all tier quotas.
    Called by the monthly cron on the 1st of each month, before quota-reset on auth-service.
    """
    updated = await tier_service.apply_pending_quotas(session)
    return {"message": "Billing cycle reset complete", "quotas_updated": updated}


@router.get("/services/{service_id:path}", include_in_schema=False)
async def internal_get_service_detail(
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
):
    """Full, unfiltered service detail (incl. model.adapter_config) for
    callers inside the cluster, e.g. inference-service resolving a Triton
    endpoint. The public /api/v1/services/{id} strips model/adapter_config
    for non-admin callers (AI4IDS-1816); this route is not proxied by the
    gateway (see infrastructure/nginx/nginx.conf) so it's safe to leave
    unfiltered here.
    """
    try:
        validate_service_id(service_id)
    except ValueError as exc:
        raise ValidationError(message=str(exc), code="INVALID_SERVICE_ID")
    data = await svc.get_service_detail(service_id)
    return success_response(data=data)
