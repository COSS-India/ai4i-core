"""Internal endpoints — service-to-service calls, not exposed to end users."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.dependencies.services import ServiceService, get_service_service
from app.schemas.model_management.service import (
    GetServiceResponse,
    validate_service_id,
)
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
async def get_service_detail_internal(
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
) -> GetServiceResponse:
    """
    Full, unfiltered service detail for inference-service's own resolver
    (InferenceServerResolver._query_model_management_service) — the only
    caller of this route.

    GET /api/v1/services/{service_id} strips `api_key`/`inferenceApiKey`
    for any caller without ADMIN/MODERATOR permission IDs
    (routes/service.py::_filter_service_fields, AI4IDS-1816). That request
    is identity-aware — it's forwarded from an end user via the gateway,
    which attaches X-Permission-IDS after JWT validation.

    inference-service's resolver is not a user request being forwarded —
    it's this service calling out on its own, with no per-request identity
    to attach. Calling the public route always looked "non-admin" to that
    filter and silently dropped api_key/inferenceApiKey — so a service
    configured with a Triton or vLLM auth token would resolve with
    api_key=None every time, and inference-service would call the
    upstream model server with no Authorization header regardless of
    what was configured (see task_service.py::_call_triton_inference and
    llm_service.py::forward/open_stream/proxy_multipart, both of which
    depend on service_info["api_key"] actually being populated).

    This route exists instead of teaching the public route to recognize
    inference-service, because that would mean inventing a way for an
    identity-less caller to prove it's a trusted internal service — the
    same trust boundary /internal already establishes for every other
    route in this file (network-level: not exposed to end users, same as
    /internal/ppu/billing-cycle-reset above). Reusing it keeps this
    service's one existing "trusted machine caller" boundary, instead of
    a second one with different rules.
    """
    try:
        validate_service_id(service_id)
    except ValueError as exc:
        raise ValidationError(message=str(exc), code="INVALID_SERVICE_ID")
    data = await svc.get_service_detail(service_id)
    return GetServiceResponse(success=True, data=data)
