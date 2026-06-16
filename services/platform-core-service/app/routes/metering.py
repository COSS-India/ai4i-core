"""Prometheus metrics query endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.dependencies.services import get_metering_service
from app.services.metering_service import MeteringService
from app.utils.metering_promql_builder import TIME_RANGES, SERVICE_BREAKDOWN_CONFIG

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


class TenantRankingFilter(_LimitMixin, _TimeRangeBase):
    limit: int = 10


class ThroughputFilter(_TimeRangeBase):
    tenant: Optional[str] = None
    service_id: Optional[str] = None
    inference_only: bool = True


class TopTenantsThroughputFilter(_LimitMixin, _TimeRangeBase):
    limit: int = 10
    inference_only: bool = True


class TenantCountFilter(_TimeRangeBase):
    pass


class UsageByTenantServiceFilter(_LimitMixin, _TimeRangeBase):
    limit: int = 10
    services: Optional[list[str]] = None

    @field_validator("services")
    @classmethod
    def validate_services(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v:
            valid = set(SERVICE_BREAKDOWN_CONFIG)
            invalid = [s for s in v if s not in valid]
            if invalid:
                raise ValueError(f"Invalid services: {invalid}. Allowed: {sorted(valid)}")
        return v


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


@router.post("/tenant-ranking")
async def get_tenant_ranking(
    body: TenantRankingFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.tenant_ranking(body.limit, body.time_range)


@router.post("/throughput")
async def get_throughput(
    body: ThroughputFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.throughput(body.inference_only, body.tenant, body.service_id, body.time_range)


@router.post("/top-tenants-throughput")
async def get_top_tenants_throughput(
    body: TopTenantsThroughputFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.top_tenants_throughput(body.limit, body.inference_only, body.time_range)


@router.post("/tenant-count")
async def get_tenant_count(
    body: TenantCountFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.tenant_count(body.time_range)


@router.post("/usage-by-tenant-service")
async def get_usage_by_tenant_service(
    body: UsageByTenantServiceFilter,
    svc: MeteringService = Depends(get_metering_service),
):
    return await svc.usage_by_tenant_service(body.limit, body.time_range, body.services)
