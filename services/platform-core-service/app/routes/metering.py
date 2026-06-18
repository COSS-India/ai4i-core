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
    OverviewResponse,
    PlatformAdoption,
    Scope,
    ServiceConsumptionResponse,
    ServiceRow,
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


async def _request_volume_chart(
    svc: MeteringService,
    window: str,
    tenant: Optional[str],
) -> Optional[Graph]:
    if window not in WINDOW_STEP:
        return None
    from app.utils.metering_promql_builder import build_base_selectors

    sel = build_base_selectors(inference_only=True, tenant=tenant)
    metric = f"telemetry_obsv_requests_total{sel}"
    step = WINDOW_STEP[window]
    w_secs = _WINDOW_SECONDS[window]
    now = _time.time()

    results = await svc._client.query_range(
        f"sum(rate({metric}[1m]))",
        start=now - w_secs,
        end=now,
        step=step,
    )
    if not results:
        return None

    points = [
        GraphPoint(ts=int(ts), value=round(float(val), 4))
        for ts, val in results[0].get("values", [])
    ]
    return Graph(
        step=step,
        series=[GraphSeries(key="requests", label="Request Rate (RPS)", points=points)],
    )


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
        _request_volume_chart(svc, window, scope_tenant),
        svc.usage_concentration(limit=5, time_range=window) if is_admin else _noop(),
        svc.tenant_ranking(limit=5, time_range=window) if is_admin else _noop(),
        return_exceptions=True,
    )

    def _ok(r):
        if isinstance(r, Exception):
            logger.warning("Metering query failed: %s", r)
            nonlocal degraded
            degraded = True
            return None
        return r

    tc, at24, at7, at30, at_window, rt, tp, chart, conc, ranking = [_ok(r) for r in results]

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
        kpis.append(Cell(
            key="avg_requests_per_tenant",
            label="Avg Requests / Tenant",
            value=round(rt["total_requests"]["count"] / at_window["count"], 1),
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

    # Usage concentration block (admin only)
    usage_conc: Optional[UsageConcentration] = None
    if is_admin and conc:
        usage_conc = UsageConcentration(
            top_tenants=[
                TenantRow(
                    rank=t["rank"],
                    tenant=t["tenant"],
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

    cache_key = f"metering:tenant-consumption:{window}:{limit}"
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    degraded = False

    ranking_result, heatmap_result = await asyncio.gather(
        svc.tenant_ranking(limit=limit, time_range=window),
        svc.usage_by_tenant_service(limit=limit, time_range=window, services=None),
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

    response = TenantConsumptionResponse(
        scope=Scope(role=_caller_role_label(request), tenant_id=None, organisation=None, window=window),
        tenant_ranking=[
            TenantRow(
                rank=t["rank"],
                tenant=t["tenant"],
                requests=t["requests"],
                formatted_requests=t["formatted_requests"],
                percentage=t["percentage"],
            )
            for t in (ranking["tenants"] if ranking else [])
        ],
        usage_by_service=heatmap["tenants"] if heatmap else [],
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

    cache_key = f"metering:service-consumption:{window}:{scope_tenant or 'all'}:{_caller_role_label(request)}"
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    degraded = False

    breakdown_result, tp_result, chart_result = await asyncio.gather(
        svc.service_breakdown(tenant=scope_tenant, time_range=window),
        svc.throughput(inference_only=True, tenant=scope_tenant, service_id=None, time_range=window),
        _request_volume_chart(svc, window, scope_tenant),
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

    response = ServiceConsumptionResponse(
        scope=Scope(role=_caller_role_label(request), tenant_id=scope_tenant, organisation=org, window=window),
        service_breakdown=[
            ServiceRow(
                service=s["service"],
                metering_unit=s["metering_unit"],
                requests=s["requests"],
                native_units=s["native_units"],
                native_unit_suffix=s["native_unit_suffix"],
                success_pct=s["success_pct"],
                failed=s["failed"],
                vs_prev_period_pct=s["vs_prev_period_pct"],
            )
            for s in (breakdown["services"] if breakdown else [])
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
