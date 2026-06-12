"""Prometheus metrics query endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.core.config import settings
from app.utils.prometheus_client import PrometheusClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["Metrics"])

_INFERENCE_ENDPOINT_REGEX = r".*inference.*"

# Allowed time range values mapped to Prometheus duration strings.
# "all" means no time window — returns the cumulative counter value.
_TIME_RANGES = {
    "1h":  "1h",
    "24h": "24h",
    "7d":  "7d",
    "30d": "30d",
    "all": None,
}


def _get_prometheus_client() -> PrometheusClient:
    if not settings.prometheus_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prometheus is not configured (PROMETHEUS_URL is unset).",
        )
    return PrometheusClient(settings.prometheus_url)


def _apply_time_range(metric_expr: str, time_range: Optional[str]) -> str:
    """Wrap metric_expr in increase(...[window]) when a time range is given.

    increase() returns how much the counter grew over the window.
    When time_range is None or "all", returns the raw cumulative counter.
    """
    window = _TIME_RANGES.get(time_range or "all")
    if window:
        return f"increase({metric_expr}[{window}])"
    return metric_expr


@router.get("/requesttotal")
async def get_request_total(
    tenant: Optional[str] = Query(None, description="Filter by tenant label"),
    service_id: Optional[str] = Query(None, description="Filter by service_id label"),
    inference_only: bool = Query(True, description="Count only inference endpoints (POST .*inference.*)"),
    time_range: Optional[str] = Query(None, description="Time window: 1h | 24h | 7d | 30d | all (default: all)"),
):
    """Return total request count from Prometheus.

    Use `time_range` to filter by a rolling window:
    - `1h`  → requests in the last 1 hour
    - `24h` → requests in the last 24 hours
    - `7d`  → requests in the last 7 days
    - `30d` → requests in the last 30 days
    - `all` → cumulative total since service started (default)
    """
    if time_range and time_range not in _TIME_RANGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid time_range '{time_range}'. Allowed: {list(_TIME_RANGES)}",
        )

    selectors = []
    if inference_only:
        selectors.append(f'endpoint=~"{_INFERENCE_ENDPOINT_REGEX}"')
        selectors.append('method="POST"')
    if tenant:
        selectors.append(f'tenant="{tenant}"')
    if service_id:
        selectors.append(f'service_id="{service_id}"')

    label_str = "{" + ",".join(selectors) + "}" if selectors else ""
    metric = f"telemetry_obsv_requests_total{label_str}"
    promql = f"sum({_apply_time_range(metric, time_range)})"

    client = _get_prometheus_client()
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


@router.get("/top-inference-services")
async def get_top_inference_services(
    limit: int = Query(10, ge=1, le=50, description="Number of top services to return"),
    tenant: Optional[str] = Query(None, description="Filter by tenant label"),
    time_range: Optional[str] = Query(None, description="Time window: 1h | 24h | 7d | 30d | all (default: all)"),
):
    """Return inference endpoints ranked by total request count (most called first).

    Use `time_range` to rank by activity within a rolling window instead of all-time.
    """
    if time_range and time_range not in _TIME_RANGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid time_range '{time_range}'. Allowed: {list(_TIME_RANGES)}",
        )

    selectors = [
        f'endpoint=~"{_INFERENCE_ENDPOINT_REGEX}"',
        'method="POST"',
    ]
    if tenant:
        selectors.append(f'tenant="{tenant}"')

    label_str = "{" + ",".join(selectors) + "}"
    metric = f"telemetry_obsv_requests_total{label_str}"
    promql = f"topk({limit}, sum by(endpoint) ({_apply_time_range(metric, time_range)}))"

    client = _get_prometheus_client()
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
