"""Metering dashboard tab endpoints — 3 GET routes, one per tab."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time as _time
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text

from app.core.config import settings
from app.core.exceptions import InsufficientPermissionsError
from app.core.redis import get_redis
from app.dependencies.services import get_metering_service
from app.schemas.metering import (
    Cell,
    Graph,
    GraphPoint,
    GraphSeries,
    HighestFailureService,
    MostUsedService,
    OverviewResponse,
    PlatformAdoption,
    RequestHealth,
    Scope,
    ServiceConsumptionResponse,
    ServiceRow,
    ServiceSummary,
    TenantConsumptionResponse,
    TenantRow,
    ThroughputData,
    UsageConcentration,
)
from app.services.metering_service import MeteringService
from app.utils.metering_promql_builder import TIME_RANGES, WINDOW_STEP

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metering", tags=["Metering"])

_ROLE_ADMIN = 1
_ROLE_MODERATOR = 2
_ROLE_TENANT_ADMIN = 5

_CACHE_TTL = settings.metering_cache_ttl_seconds

_WINDOW_SECONDS: dict = {
    "1h":  3_600,
    "24h": 86_400,
    "7d":  604_800,
    "30d": 2_592_000,
}


# ── Auth helpers ─────────────────────────────────────────────────────────────


def _permission_ids(request: Request) -> set[int]:
    raw = request.headers.get("X-Permission-IDS", "")
    return {int(m) for m in re.findall(r"\d+", raw)}


def _require_metering_access(request: Request) -> None:
    ids = _permission_ids(request)
    if not ids & {_ROLE_ADMIN, _ROLE_MODERATOR, _ROLE_TENANT_ADMIN}:
        raise InsufficientPermissionsError()


def _is_platform_admin(request: Request) -> bool:
    return bool(_permission_ids(request) & {_ROLE_ADMIN, _ROLE_MODERATOR})


def _caller_tenant_id(request: Request) -> Optional[str]:
    return request.headers.get("X-Tenant-Id") or None


def _validate_scope_tenant(tenant_id: Optional[str]) -> Optional[str]:
    if tenant_id is not None and not re.fullmatch(r"[0-9]+", tenant_id):
        raise HTTPException(status_code=400, detail="tenant_id must be a positive integer")
    return tenant_id


def _caller_role_label(request: Request) -> str:
    ids = _permission_ids(request)
    if ids & {_ROLE_ADMIN, _ROLE_MODERATOR}:
        return "admin"
    if _ROLE_TENANT_ADMIN in ids:
        return "tenant_admin"
    return "unknown"


# ── Cache helpers ─────────────────────────────────────────────────────────────


async def _cache_get(redis: aioredis.Redis, key: str) -> Optional[dict]:
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def _cache_set(redis: aioredis.Redis, key: str, data: dict) -> None:
    try:
        await redis.set(key, json.dumps(data), ex=_CACHE_TTL)
    except Exception:
        pass


# ── Shared helpers ────────────────────────────────────────────────────────────


async def _resolve_org(svc: MeteringService, tenant_id: str) -> Optional[str]:
    if svc._auth_db is None or not tenant_id:
        return None
    try:
        row = await svc._auth_db.execute(
            text("SELECT organisation FROM tenants WHERE id = :id"),
            {"id": int(tenant_id)},
        )
        return row.scalar()
    except Exception:
        return None


def _series_points(res, ndigits: int) -> list[GraphPoint]:
    """Build GraphPoints from a query_range result, skipping NaN/Inf samples."""
    if isinstance(res, Exception) or not res:
        return []
    out: list[GraphPoint] = []
    for ts, val in res[0].get("values", []):
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        if f != f or f in (float("inf"), float("-inf")):  # NaN / ±Inf
            continue
        out.append(GraphPoint(ts=int(ts), value=round(f, ndigits)))
    return out


async def _request_health_chart(
    svc: MeteringService,
    window: str,
    tenant: Optional[str],
) -> Optional[Graph]:
    """OVERVIEW "Request Volume & Health" chart — two series:
      - "requests"     : request COUNT per bucket (left axis)
      - "failure_rate" : failure rate % per bucket (right axis)
    """
    if window not in WINDOW_STEP:
        return None
    from app.utils.metering_promql_builder import build_base_selectors

    sel = build_base_selectors(inference_only=True, tenant=tenant)
    failed_sel = build_base_selectors(
        inference_only=True, tenant=tenant, extra=['status_code=~"[45].."']
    )
    metric = f"telemetry_obsv_requests_total{sel}"
    failed_metric = f"telemetry_obsv_requests_total{failed_sel}"
    step = WINDOW_STEP[window]
    w_secs = _WINDOW_SECONDS[window]
    now = _time.time()
    start = now - w_secs

    count_q = f"sum(increase({metric}[{step}]))"
    failure_rate_q = f"100 * sum(rate({failed_metric}[{step}])) / sum(rate({metric}[{step}]))"

    count_res, fr_res = await asyncio.gather(
        svc._client.query_range(count_q, start=start, end=now, step=step),
        svc._client.query_range(failure_rate_q, start=start, end=now, step=step),
        return_exceptions=True,
    )

    req_points = _series_points(count_res, 0)        # counts
    fr_points = _series_points(fr_res, 2)            # percent

    if not req_points and not fr_points:
        return None

    series = [GraphSeries(key="requests", label="Requests", points=req_points)]
    if fr_points:
        series.append(GraphSeries(key="failure_rate", label="Failure Rate %", points=fr_points))
    return Graph(step=step, series=series)


async def _throughput_chart(
    svc: MeteringService,
    window: str,
    tenant: Optional[str],
) -> Optional[Graph]:
    """TENANT/SERVICE CONSUMPTION "Throughput & Load" chart — RPS over time.

    Single "requests" series in requests/second (the avg/peak reference values
    come from the separate throughput() block).
    """
    if window not in WINDOW_STEP:
        return None
    from app.utils.metering_promql_builder import build_base_selectors

    sel = build_base_selectors(inference_only=True, tenant=tenant)
    metric = f"telemetry_obsv_requests_total{sel}"
    step = WINDOW_STEP[window]
    w_secs = _WINDOW_SECONDS[window]
    now = _time.time()

    res = await svc._client.query_range(
        f"sum(rate({metric}[{step}]))",
        start=now - w_secs,
        end=now,
        step=step,
    )
    points = _series_points(res, 4)
    if not points:
        return None
    return Graph(
        step=step,
        series=[GraphSeries(key="requests", label="Request Rate (RPS)", points=points)],
    )


async def _resolve_orgs(svc: MeteringService, tenant_ids: list[str]) -> dict:
    """Batch-resolve tenant id -> organisation name from the auth DB.

    Ids are pre-sanitized numeric strings; cast to int for the IN-list. Returns
    {} when the auth DB is unavailable so callers fall back to the id.
    """
    numeric = [int(t) for t in tenant_ids if t and t.isdigit()]
    if svc._auth_db is None or not numeric:
        return {}
    try:
        rows = await svc._auth_db.execute(
            text("SELECT id, organisation FROM tenants WHERE id = ANY(:ids)"),
            {"ids": numeric},
        )
        return {str(r[0]): r[1] for r in rows.all()}
    except Exception:
        return {}


def _validate_window(window: str) -> None:
    if window not in TIME_RANGES or window == "all":
        raise HTTPException(
            status_code=400,
            detail=f"Invalid window '{window}'. Allowed: 1h, 24h, 7d, 30d",
        )


# ── Tab 1: Overview ───────────────────────────────────────────────────────────


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    request: Request,
    window: str = Query("24h", description="Time window: 1h | 24h | 7d | 30d"),
    tenant_id: Optional[str] = Query(None, description="Narrow to a specific tenant (admin only)"),
    svc: MeteringService = Depends(get_metering_service),
    redis: aioredis.Redis = Depends(get_redis),
):
    _require_metering_access(request)
    _validate_window(window)

    is_admin = _is_platform_admin(request)
    caller_tid = _caller_tenant_id(request)
    scope_tenant = _validate_scope_tenant(caller_tid if not is_admin else (tenant_id or None))

    cache_key = f"metering:overview:{window}:{scope_tenant or 'all'}:{_caller_role_label(request)}"
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    degraded = False

    async def _noop():
        return None

    results = await asyncio.gather(
        svc.tenant_count(),
        svc.active_tenants("24h"),
        svc.active_tenants("7d"),
        svc.active_tenants("30d"),
        svc.active_tenants(window),   # window-scoped, used as avg_requests_per_tenant denominator
        svc.request_total(inference_only=True, tenant=scope_tenant, service_id=None, time_range=window),
        svc.throughput(inference_only=True, tenant=scope_tenant, service_id=None, time_range=window),
        _request_health_chart(svc, window, scope_tenant),
        svc.usage_concentration(limit=5, time_range=window) if is_admin else _noop(),
        svc.tenant_ranking(limit=5, time_range=window) if is_admin else _noop(),
        svc.active_tenants_count_previous(window),  # prev-window denominator for avg/tenant trend
        return_exceptions=True,
    )

    def _ok(r):
        if isinstance(r, Exception):
            logger.warning("Metering query failed: %s", r)
            nonlocal degraded
            degraded = True
            return None
        return r

    tc, at24, at7, at30, at_window, rt, tp, chart, conc, ranking, prev_active = [_ok(r) for r in results]

    org = await _resolve_org(svc, scope_tenant) if scope_tenant else None

    # KPI cells
    kpis: list[Cell] = []
    if rt:
        kpis.extend([
            Cell(
                key="total_requests",
                label="Total Requests",
                value=rt["total_requests"]["formatted"],
                pct_change=rt["total_requests"]["vs_previous_pct"],
            ),
            Cell(
                key="success_rate",
                label="Success Rate",
                value=rt["success_rate"]["rate_pct"],
                pct_change=rt["success_rate"]["vs_previous_pct"],
            ),
            Cell(
                key="avg_rps",
                label="Avg RPS",
                value=rt["avg_rps"]["value"],
                pct_change=rt["avg_rps"]["vs_previous_pct"],
            ),
        ])
    if is_admin and rt and at_window and at_window.get("count"):
        avg_per_tenant = round(rt["total_requests"]["count"] / at_window["count"], 1)
        # Trend vs previous window: prev avg = prev_total / prev_active_tenants.
        avg_pct_change = None
        prev_total = rt["total_requests"].get("previous_count")
        if prev_total and prev_active:
            prev_avg = prev_total / prev_active
            if prev_avg > 0:
                avg_pct_change = round((avg_per_tenant - prev_avg) / prev_avg * 100, 1)
        kpis.append(Cell(
            key="avg_requests_per_tenant",
            label="Avg Requests / Tenant",
            value=avg_per_tenant,
            pct_change=avg_pct_change,
        ))

    active_cells: list[Cell] = [
        Cell(key="active_24h", label="Active Tenants (24h)", value=at24["count"] if at24 else None),
        Cell(key="active_7d",  label="Active Tenants (7d)",  value=at7["count"]  if at7  else None),
        Cell(key="active_30d", label="Active Tenants (30d)", value=at30["count"] if at30 else None),
    ]

    # Platform adoption block (admin only)
    platform_adoption: Optional[PlatformAdoption] = None
    if is_admin and tc:
        platform_adoption = PlatformAdoption(
            total_tenants=tc["total_tenants"],
            new_tenants_7d=tc["new_tenants"],
            active_24h=at24["count"] if at24 else None,
            active_7d=at7["count"] if at7 else None,
            active_30d=at30["count"] if at30 else None,
        )

    # Request Volume & Health — total / successful / failed counts + rates
    request_health: Optional[RequestHealth] = None
    if rt:
        request_health = RequestHealth(
            total=rt["total_requests"]["count"],
            successful=rt["successful_requests"]["count"],
            failed=rt["failed_requests"]["count"],
            total_formatted=rt["total_requests"]["formatted"],
            successful_formatted=rt["successful_requests"]["formatted"],
            failed_formatted=rt["failed_requests"]["formatted"],
            success_rate_pct=rt["success_rate"]["rate_pct"],
            failure_rate_pct=rt["failure_rate"]["rate_pct"],
        )

    # Usage concentration block (admin only) — resolve org names in one batched query
    usage_conc: Optional[UsageConcentration] = None
    if is_admin and conc:
        org_map = await _resolve_orgs(svc, [t["tenant"] for t in conc["top_tenants"]])
        usage_conc = UsageConcentration(
            top_tenants=[
                TenantRow(
                    rank=t["rank"],
                    tenant=t["tenant"],
                    organisation=org_map.get(t["tenant"]),
                    requests=t["requests"],
                    formatted_requests=MeteringService._format_count(t["requests"]),
                    percentage=t["percentage"],
                )
                for t in conc["top_tenants"]
            ],
            others=conc["others"],
            top_concentration_pct=conc["top_concentration_percentage"],
            grand_total=conc["grand_total"],
        )

    response = OverviewResponse(
        scope=Scope(role=_caller_role_label(request), tenant_id=scope_tenant, organisation=org, window=window),
        kpis=kpis,
        active_tenants=active_cells,
        platform_adoption=platform_adoption,
        usage_concentration=usage_conc,
        request_health=request_health,
        request_volume=chart,
        throughput=ThroughputData(
            avg_rps=tp["avg_rps"] if tp else 0.0,
            peak_rps=tp.get("peak_rps") if tp else None,
            peak_at=tp.get("peak_at") if tp else None,
        ),
        degraded=degraded,
        generated_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    if not degraded:
        await _cache_set(redis, cache_key, response.model_dump())

    return response


# ── Tab 2: Tenant Consumption ─────────────────────────────────────────────────


@router.get("/tenant-consumption", response_model=TenantConsumptionResponse)
async def get_tenant_consumption(
    request: Request,
    window: str = Query("24h", description="Time window: 1h | 24h | 7d | 30d"),
    limit: int = Query(10, ge=1, le=50, description="Max tenants to return"),
    services: Optional[str] = Query(
        None, description="Comma-separated service keys for the heatmap columns (default: all)"
    ),
    svc: MeteringService = Depends(get_metering_service),
    redis: aioredis.Redis = Depends(get_redis),
):
    _require_metering_access(request)

    if not _is_platform_admin(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admins cannot access tenant consumption.",
        )

    _validate_window(window)

    service_filter = [s.strip() for s in services.split(",") if s.strip()] if services else None

    cache_key = f"metering:tenant-consumption:{window}:{limit}:{services or 'all'}"
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    degraded = False

    # Platform-wide (admin-only endpoint): tenant=None throughout.
    ranking_result, heatmap_result, tp_result, chart_result = await asyncio.gather(
        svc.tenant_ranking(limit=limit, time_range=window),
        svc.usage_by_tenant_service(limit=limit, time_range=window, services=service_filter),
        svc.throughput(inference_only=True, tenant=None, service_id=None, time_range=window),
        _throughput_chart(svc, window, None),
        return_exceptions=True,
    )

    def _ok(r):
        if isinstance(r, Exception):
            logger.warning("Metering query failed: %s", r)
            nonlocal degraded
            degraded = True
            return None
        return r

    ranking = _ok(ranking_result)
    heatmap = _ok(heatmap_result)
    tp = _ok(tp_result)
    chart = _ok(chart_result)

    ranking_tenants = ranking["tenants"] if ranking else []
    heatmap_rows = heatmap["tenants"] if heatmap else []

    # Batched auth-DB lookups: organisation names (both lists) + plan tier (ranking).
    all_ids = list({t["tenant"] for t in ranking_tenants} | {r["tenant"] for r in heatmap_rows})
    org_map = await _resolve_orgs(svc, all_ids)

    for r in heatmap_rows:
        r["organisation"] = org_map.get(r["tenant"])

    response = TenantConsumptionResponse(
        scope=Scope(role=_caller_role_label(request), tenant_id=None, organisation=None, window=window),
        tenant_ranking=[
            TenantRow(
                rank=t["rank"],
                tenant=t["tenant"],
                organisation=org_map.get(t["tenant"]),
                requests=t["requests"],
                formatted_requests=t["formatted_requests"],
                percentage=t["percentage"],
            )
            for t in ranking_tenants
        ],
        usage_by_service=heatmap_rows,
        throughput=ThroughputData(
            avg_rps=tp["avg_rps"] if tp else 0.0,
            peak_rps=tp.get("peak_rps") if tp else None,
            peak_at=tp.get("peak_at") if tp else None,
        ),
        request_volume=chart,
        degraded=degraded,
        generated_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    if not degraded:
        await _cache_set(redis, cache_key, response.model_dump())

    return response


# ── Tab 3: Service Consumption ────────────────────────────────────────────────


@router.get("/service-consumption", response_model=ServiceConsumptionResponse)
async def get_service_consumption(
    request: Request,
    window: str = Query("24h", description="Time window: 1h | 24h | 7d | 30d"),
    tenant_id: Optional[str] = Query(None, description="Narrow to a specific tenant (admin only)"),
    svc: MeteringService = Depends(get_metering_service),
    redis: aioredis.Redis = Depends(get_redis),
):
    _require_metering_access(request)
    _validate_window(window)

    is_admin = _is_platform_admin(request)
    caller_tid = _caller_tenant_id(request)
    scope_tenant = _validate_scope_tenant(caller_tid if not is_admin else (tenant_id or None))

    cache_key = f"metering:service-consumption:{window}:{scope_tenant or 'all'}:{_caller_role_label(request)}"
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    degraded = False

    breakdown_result, tp_result, chart_result = await asyncio.gather(
        svc.service_breakdown(tenant=scope_tenant, time_range=window),
        svc.throughput(inference_only=True, tenant=scope_tenant, service_id=None, time_range=window),
        _throughput_chart(svc, window, scope_tenant),
        return_exceptions=True,
    )

    def _ok(r):
        if isinstance(r, Exception):
            logger.warning("Metering query failed: %s", r)
            nonlocal degraded
            degraded = True
            return None
        return r

    breakdown = _ok(breakdown_result)
    tp = _ok(tp_result)
    chart = _ok(chart_result)

    org = await _resolve_org(svc, scope_tenant) if scope_tenant else None

    services = breakdown["services"] if breakdown else []
    total_reqs = sum(s["requests"] for s in services)

    # Summary KPIs — computed over services with traffic (a 0-request service
    # must not win "highest failure rate").
    summary: Optional[ServiceSummary] = None
    if breakdown is not None:
        active = [s for s in services if s["requests"] > 0]
        most_used = max(active, key=lambda s: s["requests"]) if active else None
        worst = max(active, key=lambda s: 100 - s["success_pct"]) if active else None
        summary = ServiceSummary(
            active_services=len(active),
            most_used=(
                MostUsedService(service=most_used["service"], requests=most_used["requests"])
                if most_used else None
            ),
            highest_failure_rate=(
                HighestFailureService(
                    service=worst["service"],
                    failure_rate_pct=round(100 - worst["success_pct"], 2),
                )
                if worst else None
            ),
        )

    response = ServiceConsumptionResponse(
        scope=Scope(role=_caller_role_label(request), tenant_id=scope_tenant, organisation=org, window=window),
        summary=summary,
        service_breakdown=[
            ServiceRow(
                service=s["service"],
                metering_unit=s["metering_unit"],
                requests=s["requests"],
                percentage=round(s["requests"] / total_reqs * 100, 2) if total_reqs else 0.0,
                native_units=s["native_units"],
                native_unit_suffix=s["native_unit_suffix"],
                success_pct=s["success_pct"],
                failure_rate_pct=round(100 - s["success_pct"], 2),
                failed=s["failed"],
                vs_prev_period_pct=s["vs_prev_period_pct"],
            )
            for s in services
        ],
        throughput=ThroughputData(
            avg_rps=tp["avg_rps"] if tp else 0.0,
            peak_rps=tp.get("peak_rps") if tp else None,
            peak_at=tp.get("peak_at") if tp else None,
        ),
        request_volume=chart,
        degraded=degraded,
        generated_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    if not degraded:
        await _cache_set(redis, cache_key, response.model_dump())

    return response
