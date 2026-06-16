"""Prometheus metrics query endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.dependencies.services import get_metering_service
from app.services.metering_service import MeteringService
from app.utils.metering_promql_builder import TIME_RANGES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metering", tags=["Metering"])


# ── request body models ─────────────────────────────────────────────────────

class _TimeRangeBase(BaseModel):
    time_range: Optional[str] = None

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in TIME_RANGES:
            raise ValueError(f"Invalid time_range '{v}'. Allowed: {list(TIME_RANGES)}")
        return v


class _LimitMixin(BaseModel):
    limit: int

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError("limit must be between 1 and 50")
        return v


class ActiveTenantsFilter(_TimeRangeBase):
    pass


class AvgRequestsPerTenantFilter(_TimeRangeBase):
    pass


class RequestTotalFilter(_TimeRangeBase):
    tenant: Optional[str] = None
    service_id: Optional[str] = None
    inference_only: bool = True


class TopInferenceServicesFilter(_LimitMixin, _TimeRangeBase):
    limit: int = 10
    tenant: Optional[str] = None


class UsageConcentrationFilter(_LimitMixin, _TimeRangeBase):
    limit: int = 5


class ServiceBreakdownFilter(_TimeRangeBase):
    tenant: Optional[str] = None


# ── routes ──────────────────────────────────────────────────────────────────

@router.post("/requesttotal")
async def get_request_total(
    body: RequestTotalFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.request_total(body.inference_only, body.tenant, body.service_id, body.time_range)


@router.post("/active-tenants")
async def get_active_tenants(
    body: ActiveTenantsFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.active_tenants(body.time_range)


@router.post("/avg-requests-per-tenant")
async def get_avg_requests_per_tenant(
    body: AvgRequestsPerTenantFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.avg_requests_per_tenant(body.time_range)


@router.post("/top-inference-services")
async def get_top_inference_services(
    body: TopInferenceServicesFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.top_inference_services(body.limit, body.tenant, body.time_range)


@router.post("/usage-concentration")
async def get_usage_concentration(
    body: UsageConcentrationFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.usage_concentration(body.limit, body.time_range)


@router.post("/request-volume-health")
async def get_request_volume_health(
    body: RequestTotalFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.request_volume_health(body.inference_only, body.tenant, body.service_id, body.time_range)


@router.post("/service-breakdown")
async def get_service_breakdown(
    body: ServiceBreakdownFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.service_breakdown(body.tenant, body.time_range)
