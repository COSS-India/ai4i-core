"""Prometheus metrics query endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.dependencies.services import get_prometheus_client
from app.utils.prometheus_client import PrometheusClient
from app.utils.metering_promql_builder import (
    INFERENCE_ENDPOINT_REGEX,
    TIME_RANGES,
    apply_time_range,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metering", tags=["Metering"])


def _check_time_range(v: Optional[str]) -> Optional[str]:
    if v and v not in TIME_RANGES:
        raise ValueError(f"Invalid time_range '{v}'. Allowed: {list(TIME_RANGES)}")
    return v


class ActiveTenantsFilter(BaseModel):
    time_range: Optional[str] = None

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, v):
        return _check_time_range(v)


class RequestTotalFilter(BaseModel):
    tenant: Optional[str] = None
    service_id: Optional[str] = None
    inference_only: bool = True
    time_range: Optional[str] = None

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, v):
        return _check_time_range(v)


class AvgRequestsPerTenantFilter(BaseModel):
    time_range: Optional[str] = None

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, v):
        return _check_time_range(v)


class TopInferenceServicesFilter(BaseModel):
    limit: int = 10
    tenant: Optional[str] = None
    time_range: Optional[str] = None

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v):
        if not (1 <= v <= 50):
            raise ValueError("limit must be between 1 and 50")
        return v

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, v):
        return _check_time_range(v)


class UsageConcentrationFilter(BaseModel):
    limit: int = 5
    time_range: Optional[str] = None

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v):
        if not (1 <= v <= 50):
            raise ValueError("limit must be between 1 and 50")
        return v

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, v):
        return _check_time_range(v)


@router.post("/requesttotal")
async def get_request_total(
    body: RequestTotalFilter,
    client: PrometheusClient = Depends(get_prometheus_client),
):
    """Return total inference request count, optionally filtered by tenant/service and rolling time window."""
    selectors = []
    if body.inference_only:
        selectors.append(f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"')
        selectors.append('method="POST"')
    if body.tenant:
        selectors.append(f'tenant="{body.tenant}"')
    if body.service_id:
        selectors.append(f'service_id="{body.service_id}"')

    label_str = "{" + ",".join(selectors) + "}" if selectors else ""
    metric = f"telemetry_obsv_requests_total{label_str}"
    promql = f"sum({apply_time_range(metric, body.time_range)})"

    total = await client.scalar(promql)

    return {
        "total_requests": int(total),
        "filters": {
            "inference_only": body.inference_only,
            "tenant": body.tenant,
            "service_id": body.service_id,
            "time_range": body.time_range or "all",
        },
        "promql": promql,
    }


@router.post("/active-tenants")
async def get_active_tenants(
    body: ActiveTenantsFilter,
    client: PrometheusClient = Depends(get_prometheus_client),
):
    """Return tenants that made at least one inference request in the given time window."""
    selectors = [
        f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"',
        'method="POST"',
    ]
    metric = "telemetry_obsv_requests_total{" + ",".join(selectors) + "}"
    window = body.time_range
    if window and window != "all":
        windowed = apply_time_range(metric, window)
        # OR clause rescues brand-new series missed by increase() (no prior scrape point at offset)
        promql = (
            f"sum by(tenant) ({windowed}) > 0"
            f" or (sum by(tenant) ({metric}) unless (sum by(tenant) ({metric} offset {window}) > 0))"
        )
    else:
        promql = f"sum by(tenant) ({metric}) > 0"

    results = await client.query(promql)
    tenants = [
        {
            "tenant": r["metric"].get("tenant", "unknown"),
            "request_count": int(float(r["value"][1])),
        }
        for r in results
    ]

    return {
        "active_tenants": tenants,
        "count": len(tenants),
        "filters": {"time_range": body.time_range or "all"},
        "promql": promql,
    }


@router.post("/avg-requests-per-tenant")
async def get_avg_requests_per_tenant(
    body: AvgRequestsPerTenantFilter,
    client: PrometheusClient = Depends(get_prometheus_client),
):
    """Return average inference requests per tenant over the given time window."""
    selectors = [
        f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"',
        'method="POST"',
    ]
    metric = "telemetry_obsv_requests_total{" + ",".join(selectors) + "}"
    windowed = apply_time_range(metric, body.time_range)
    promql = f"avg(sum by(tenant) ({windowed}))"

    avg = await client.scalar(promql)

    return {
        "avg_requests_per_tenant": round(float(avg), 2),
        "filters": {"time_range": body.time_range or "all"},
        "promql": promql,
    }


@router.post("/top-inference-services")
async def get_top_inference_services(
    body: TopInferenceServicesFilter,
    client: PrometheusClient = Depends(get_prometheus_client),
):
    """Return inference endpoints ranked by request count, optionally scoped to a rolling time window."""
    selectors = [
        f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"',
        'method="POST"',
    ]
    if body.tenant:
        selectors.append(f'tenant="{body.tenant}"')

    label_str = "{" + ",".join(selectors) + "}"
    metric = f"telemetry_obsv_requests_total{label_str}"
    promql = f"topk({body.limit}, sum by(endpoint) ({apply_time_range(metric, body.time_range)}))"

    results = await client.query(promql)

    services = [
        {
            "endpoint": r["metric"].get("endpoint", "unknown"),
            "total_requests": int(float(r["value"][1])),
        }
        for r in results
    ]

    grand_total = sum(s["total_requests"] for s in services)
    for s in services:
        s["percentage"] = round(s["total_requests"] / grand_total * 100, 1) if grand_total else 0.0

    return {
        "services": services,
        "grand_total": grand_total,
        "filters": {"tenant": body.tenant, "limit": body.limit, "time_range": body.time_range or "all"},
        "promql": promql,
    }


@router.post("/usage-concentration")
async def get_usage_concentration(
    body: UsageConcentrationFilter,
    client: PrometheusClient = Depends(get_prometheus_client),
):
    """Return request share for the top N tenants and the aggregated remainder, for the given time window."""
    selectors = [
        f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"',
        'method="POST"',
    ]
    metric = "telemetry_obsv_requests_total{" + ",".join(selectors) + "}"
    windowed = apply_time_range(metric, body.time_range)
    window = TIME_RANGES.get(body.time_range or "all")

    if window:
        promql = (
            f"sum by(tenant) ({windowed}) > 0"
            f" or (sum by(tenant) ({metric}) unless (sum by(tenant) ({metric} offset {window}) > 0))"
        )
    else:
        promql = f"sum by(tenant) ({metric})"

    results = await client.query(promql)

    all_tenants = sorted(
        [
            {
                "tenant": r["metric"].get("tenant", "unknown"),
                "requests": max(1, round(float(r["value"][1]))),
            }
            for r in results
            if float(r["value"][1]) > 0
        ],
        key=lambda t: t["requests"],
        reverse=True,
    )

    grand_total = sum(t["requests"] for t in all_tenants)

    top = all_tenants[: body.limit]
    rest = all_tenants[body.limit :]

    top_tenants = [
        {
            "rank": idx + 1,
            "tenant": t["tenant"],
            "requests": t["requests"],
            "percentage": round(t["requests"] / grand_total * 100, 1) if grand_total else 0.0,
        }
        for idx, t in enumerate(top)
    ]

    others_requests = sum(t["requests"] for t in rest)
    top_concentration = round(sum(t["percentage"] for t in top_tenants), 1)

    return {
        "top_tenants": top_tenants,
        "others": {
            "count": len(rest),
            "requests": others_requests,
            "percentage": round(others_requests / grand_total * 100, 1) if grand_total else 0.0,
        },
        "top_concentration_percentage": top_concentration,
        "grand_total": grand_total,
        "filters": {"limit": body.limit, "time_range": body.time_range or "all"},
        "promql": promql,
    }
