"""Prometheus metrics query endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
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


class ActiveTenantsFilter(BaseModel):
    time_range: Optional[str] = None

    @field_validator("time_range")
    @classmethod
    def _check_time_range(cls, v):
        if v and v not in TIME_RANGES:
            raise ValueError(f"Invalid time_range '{v}'. Allowed: {list(TIME_RANGES)}")
        return v


def _validate_time_range(
    time_range: Optional[str] = Query(
        None,
        description="Time window: 1h | 24h | 7d | 30d | all (default: all)",
    )
) -> Optional[str]:
    if time_range and time_range not in TIME_RANGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid time_range '{time_range}'. Allowed: {list(TIME_RANGES)}",
        )
    return time_range


@router.get("/requesttotal")
async def get_request_total(
    tenant: Optional[str] = Query(None, description="Filter by tenant label"),
    service_id: Optional[str] = Query(None, description="Filter by service_id label"),
    inference_only: bool = Query(True, description="Count only inference endpoints (POST .*inference.*)"),
    time_range: Optional[str] = Depends(_validate_time_range),
    client: PrometheusClient = Depends(get_prometheus_client),
):
    """Return total request count from Prometheus.

    Use `time_range` to filter by a rolling window:
    - `1h`  → requests in the last 1 hour
    - `24h` → requests in the last 24 hours
    - `7d`  → requests in the last 7 days
    - `30d` → requests in the last 30 days
    - `all` → cumulative total since service started (default)
    """
    selectors = []
    if inference_only:
        selectors.append(f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"')
        selectors.append('method="POST"')
    if tenant:
        selectors.append(f'tenant="{tenant}"')
    if service_id:
        selectors.append(f'service_id="{service_id}"')

    label_str = "{" + ",".join(selectors) + "}" if selectors else ""
    metric = f"telemetry_obsv_requests_total{label_str}"
    promql = f"sum({apply_time_range(metric, time_range)})"

    total = await client.scalar(promql)

    return {
        "total_requests": int(total),
        "filters": {
            "inference_only": inference_only,
            "tenant": tenant,
            "service_id": service_id,
            "time_range": time_range or "all",
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
        # increase() can return 0 for a brand-new counter with only 1 scrape point.
        # The OR clause catches tenants whose counter exists NOW but had no data
        # at the start of the window (i.e., truly new tenants in this window).
        windowed = apply_time_range(metric, window)
        promql = (
            f"sum by(tenant) (clamp_min({windowed}, 0)) > 0"
            f" or (sum by(tenant) ({metric}) unless sum by(tenant) ({metric} offset {window}))"
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


@router.get("/top-inference-services")
async def get_top_inference_services(
    limit: int = Query(10, ge=1, le=50, description="Number of top services to return"),
    tenant: Optional[str] = Query(None, description="Filter by tenant label"),
    time_range: Optional[str] = Depends(_validate_time_range),
    client: PrometheusClient = Depends(get_prometheus_client),
):
    """Return inference endpoints ranked by total request count (most called first).

    Use `time_range` to rank by activity within a rolling window instead of all-time.
    """
    selectors = [
        f'endpoint=~"{INFERENCE_ENDPOINT_REGEX}"',
        'method="POST"',
    ]
    if tenant:
        selectors.append(f'tenant="{tenant}"')

    label_str = "{" + ",".join(selectors) + "}"
    metric = f"telemetry_obsv_requests_total{label_str}"
    promql = f"topk({limit}, sum by(endpoint) ({apply_time_range(metric, time_range)}))"

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
        "filters": {"tenant": tenant, "limit": limit, "time_range": time_range or "all"},
        "promql": promql,
    }
