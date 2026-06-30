"""Metering dashboard tab endpoints — 3 GET routes, one per tab."""
from __future__ import annotations

import asyncio
import json
import logging
import math
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
    Scope,
    ServiceConsumptionResponse,
    ServiceRow,
    ServiceSummary,
    TenantConsumptionResponse,
    TenantRow,
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
        if math.isnan(f) or math.isinf(f):  # NaN / ±Inf
            continue
        out.append(GraphPoint(ts=int(ts), value=round(f, ndigits)))
    return out


_STEP_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _step_seconds(step: str) -> int:
    """Parse a Prometheus duration step (e.g. '10m', '4h', '1d') to seconds."""
    m = re.fullmatch(r"(\d+)([smhd])", step.strip())
    return int(m.group(1)) * _STEP_UNIT_SECONDS[m.group(2)] if m else 0


async def _request_volume_chart(
    svc: MeteringService,
    window: str,
    tenant: Optional[str],
) -> Optional[Graph]:
    """OVERVIEW "Request Volume" chart — successful vs failed request COUNTS per bucket:
      - "successful" : 2xx request count per bucket
      - "failed"     : 4xx/5xx request count per bucket
    """
    if window not in WINDOW_STEP:
        return None
    from app.utils.metering_promql_builder import build_base_selectors

    success_sel = build_base_selectors(
        inference_only=True, tenant=tenant, extra=['status_code=~"2.."']
    )
    failed_sel = build_base_selectors(
        inference_only=True, tenant=tenant, extra=['status_code=~"[45].."']
    )
    success_metric = f"telemetry_obsv_requests_total{success_sel}"
    failed_metric = f"telemetry_obsv_requests_total{failed_sel}"
    step = WINDOW_STEP[window]
    step_secs = _step_seconds(step)
    w_secs = _WINDOW_SECONDS[window]
    now = _time.time()
    # Align the range so the LAST bucket ends at `now`. query_range places eval
    # points at start + i*step, so an unaligned start (e.g. a 30d window with a 7d
    # step — 30 isn't divisible by 7) leaves the final point short of now and the
    # most recent bucket (today's requests) is never evaluated. Snap start to a
    # whole number of buckets ending at now.
    n_buckets = max(1, -(-w_secs // step_secs)) if step_secs else 1
    start = now - n_buckets * step_secs

    # `or vector(0)` fills idle buckets with 0 so the timeline is continuous.
    # Without it increase() emits no sample for a zero-traffic bucket, the chart
    # drops it, and the axis shows gaps (missing days / jumping intervals).
    success_q = f"sum(increase({success_metric}[{step}])) or vector(0)"
    failed_q = f"sum(increase({failed_metric}[{step}])) or vector(0)"

    succ_res, fail_res = await asyncio.gather(
        svc._client.query_range(success_q, start=start, end=now, step=step),
        svc._client.query_range(failed_q, start=start, end=now, step=step),
        return_exceptions=True,
    )

    succ_points = _series_points(succ_res, 0)        # counts (zero-filled)
    fail_points = _series_points(fail_res, 0)        # counts (zero-filled)

    # Series are now dense, so emptiness can't be inferred from point count —
    # only suppress the chart when there's no real activity anywhere in the window.
    has_data = any(p.value > 0 for p in succ_points) or any(p.value > 0 for p in fail_points)
    if not has_data:
        return None

    return Graph(
        step=step,
        series=[
            GraphSeries(key="successful", label="Successful", points=succ_points),
            GraphSeries(key="failed", label="Failed", points=fail_points),
        ],
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

    # Security backstop: a tenant admin (role 5) MUST carry a tenant context — the
    # gateway injects X-Tenant-Id from the JWT. Without it, scope_tenant is None and
    # the queries below would run unscoped, leaking platform-wide aggregates. Refuse
    # rather than widen scope (defense-in-depth; the gateway should never let this
    # through, but the backstop guarantees it).
    if not is_admin and scope_tenant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin requires a tenant context (X-Tenant-Id).",
        )

    cache_key = f"metering:overview:v2:{window}:{scope_tenant or 'all'}:{_caller_role_label(request)}"
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
        svc.request_total(inference_only=True, tenant=scope_tenant, service_id=None, time_range=window),
        _request_volume_chart(svc, window, scope_tenant),
        # Usage Concentration is platform-wide top-5; hide it when a tenant filter is applied.
        svc.usage_concentration(limit=5, time_range=window) if (is_admin and not scope_tenant) else _noop(),
        return_exceptions=True,
    )

    def _ok(r):
        if isinstance(r, Exception):
            logger.warning("Metering query failed: %s", r)
            nonlocal degraded
            degraded = True
            return None
        return r

    tc, at24, at7, at30, rt, chart, conc = [_ok(r) for r in results]

    org = await _resolve_org(svc, scope_tenant) if scope_tenant else None

    # KPI cells. Successful/Failed show the COUNT as the value and the rate as
    # sub-text (helper); both are colored on the frontend (green / red).
    kpis: list[Cell] = []
    if rt:
        success_rate = rt["success_rate"]["rate_pct"]
        # No traffic → 0% failure (not 100%); 100−0 would be wrong.
        failure_rate = round(100 - success_rate, 2) if rt["total_requests"]["count"] else 0.0
        kpis.extend([
            Cell(
                key="total_requests",
                label="Total Requests",
                value=rt["total_requests"]["formatted"],
                previous=rt["total_requests"]["previous_formatted"],
                pct_change=rt["total_requests"]["vs_previous_pct"],
            ),
            Cell(
                key="successful",
                label="Successful",
                value=rt["successful_requests"]["formatted"],
                previous=rt["successful_requests"]["previous_formatted"],
                pct_change=rt["successful_requests"]["vs_previous_pct"],
                helper=f"{success_rate:.2f}% success rate",
            ),
            Cell(
                key="failed",
                label="Failed",
                value=rt["failed_requests"]["formatted"],
                previous=rt["failed_requests"]["previous_formatted"],
                pct_change=rt["failed_requests"]["vs_previous_pct"],
                helper=f"{failure_rate:.2f}% failure rate",
            ),
            Cell(
                key="avg_rps",
                label="Avg RPS (req/s)",
                value=rt["avg_rps"]["value"],
                previous=rt["avg_rps"]["previous_value"],
                pct_change=rt["avg_rps"]["vs_previous_pct"],
            ),
        ])

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

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = OverviewResponse(
        scope=Scope(role=_caller_role_label(request), tenant_id=scope_tenant, organisation=org, window=window),
        kpis=kpis,
        platform_adoption=platform_adoption,
        usage_concentration=usage_conc,
        request_volume=chart,
        degraded=degraded,
        generated_at=generated_at,
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
    tenant_id: Optional[str] = Query(None, description="Scope to a single tenant (admin only)"),
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

    # Admin-only endpoint: scope to the selected tenant when one is chosen,
    # otherwise platform-wide (tenant=None) for the cross-tenant ranking.
    scope_tenant = _validate_scope_tenant(tenant_id or None)

    service_filter = [s.strip() for s in services.split(",") if s.strip()] if services else None

    cache_key = (
        f"metering:tenant-consumption:v2:{window}:{limit}:{scope_tenant or 'all'}:{services or 'all'}"
    )
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    degraded = False

    ranking_result, heatmap_result, prev_avg_result = await asyncio.gather(
        svc.tenant_ranking(limit=limit, time_range=window, tenant=scope_tenant),
        svc.usage_by_tenant_service(
            limit=limit, time_range=window, services=service_filter, tenant=scope_tenant
        ),
        svc.avg_per_active_tenant_previous(window, tenant=scope_tenant),
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

    ranking_tenants = ranking["tenants"] if ranking else []
    heatmap_rows = heatmap["tenants"] if heatmap else []

    # Batched auth-DB lookup: organisation names for both lists.
    all_ids = list({t["tenant"] for t in ranking_tenants} | {r["tenant"] for r in heatmap_rows})
    org_map = await _resolve_orgs(svc, all_ids)

    for r in heatmap_rows:
        r["organisation"] = org_map.get(r["tenant"])

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Avg requests per active tenant — KPI card shown above the ranking.
    avg_per_tenant_cell = None
    if ranking and ranking.get("total_tenant_count"):
        prev_avg = _ok(prev_avg_result)
        cur_avg = ranking.get("avg_per_active_tenant")
        pct = (
            round((cur_avg - prev_avg) / prev_avg * 100, 1)
            if (prev_avg and cur_avg is not None) else None
        )
        avg_per_tenant_cell = Cell(
            key="avg_requests_per_tenant",
            label="Avg Requests Per Active Tenant",
            value=ranking["formatted_avg_per_active_tenant"],
            pct_change=pct,
        )

    response = TenantConsumptionResponse(
        scope=Scope(
            role=_caller_role_label(request),
            tenant_id=scope_tenant,
            organisation=org_map.get(scope_tenant) if scope_tenant else None,
            window=window,
        ),
        avg_requests_per_tenant=avg_per_tenant_cell,
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
        degraded=degraded,
        generated_at=generated_at,
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

    # Security backstop: a tenant admin (role 5) MUST carry a tenant context — the
    # gateway injects X-Tenant-Id from the JWT. Without it, scope_tenant is None and
    # the queries below would run unscoped, leaking platform-wide aggregates. Refuse
    # rather than widen scope (defense-in-depth; the gateway should never let this
    # through, but the backstop guarantees it).
    if not is_admin and scope_tenant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin requires a tenant context (X-Tenant-Id).",
        )

    cache_key = f"metering:service-consumption:v2:{window}:{scope_tenant or 'all'}:{_caller_role_label(request)}"
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    degraded = False

    breakdown_result, = await asyncio.gather(
        svc.service_breakdown(tenant=scope_tenant, time_range=window),
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

    org = await _resolve_org(svc, scope_tenant) if scope_tenant else None

    services = breakdown["services"] if breakdown else []
    # Summary KPIs — computed over services with traffic (a 0-request service
    # must not win "highest failure rate").
    summary: Optional[ServiceSummary] = None
    if breakdown is not None:
        active = [s for s in services if s["requests"] > 0]
        most_used = max(active, key=lambda s: s["requests"]) if active else None
        worst = max(active, key=lambda s: 100 - s["success_pct"]) if active else None
        summary = ServiceSummary(
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

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = ServiceConsumptionResponse(
        scope=Scope(role=_caller_role_label(request), tenant_id=scope_tenant, organisation=org, window=window),
        summary=summary,
        service_breakdown=[
            ServiceRow(
                service=s["service"],
                requests=s["requests"],
                native_units=s["native_units"],
                native_unit_suffix=s["native_unit_suffix"],
                success_pct=s["success_pct"],
                # No traffic → nothing succeeded AND nothing failed. Without this
                # guard, success_pct=0 for a 0-request service makes 100-0=100%
                # failure, which is wrong (it should be 0%).
                failure_rate_pct=round(100 - s["success_pct"], 2) if s["requests"] else 0.0,
            )
            for s in services
        ],
        degraded=degraded,
        generated_at=generated_at,
    )

    if not degraded:
        await _cache_set(redis, cache_key, response.model_dump())

    return response
