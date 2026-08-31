"""Metering dashboard tab endpoints — 3 GET routes, one per tab."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time as _time
from datetime import datetime, timezone
from typing import Literal, Optional, Union

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
    HighestFailureModel,
    HighestFailureService,
    ModelConsumptionResponse,
    ModelConsumptionSummary,
    MostUsedModel,
    MostUsedService,
    ServiceModelRow,
    OverviewResponse,
    PlatformAdoption,
    Scope,
    ServiceConsumptionResponse,
    ServiceRow,
    ServiceSummary,
    TenantConsumptionResponse,
    TenantRow,
    TopModelRow,
    UsageConcentration,
)
from app.services.metering_service import MeteringService
from app.utils.metering_promql_builder import API_KEY_AUTH_TYPE, SERVICE_BREAKDOWN_CONFIG, WINDOW_STEP

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


def _caller_tenant_name(request: Request) -> Optional[str]:
    """Organisation name for the caller's own tenant — X-Tenant-Name is the same
    value the observability middleware uses as the Prometheus ``tenant`` label,
    so it's what PromQL selectors must filter on (see build_base_selectors)."""
    return request.headers.get("X-Tenant-Name") or None


def _validate_scope_tenant(tenant_id: Optional[Union[str, int]]) -> Optional[str]:
    if tenant_id is None:
        return None
    if isinstance(tenant_id, int):
        # Query param path: already validated ge=1 by FastAPI — just coerce to str.
        return str(tenant_id)
    # Header path (X-Tenant-Id from gateway JWT): guard against malformed values.
    if not re.fullmatch(r"[0-9]+", tenant_id):
        raise HTTPException(status_code=422, detail="tenant_id must be a positive integer")
    return tenant_id


def _caller_role_label(request: Request) -> str:
    ids = _permission_ids(request)
    if ids & {_ROLE_ADMIN, _ROLE_MODERATOR}:
        return "admin"
    if _ROLE_TENANT_ADMIN in ids:
        return "tenant_admin"
    return "unknown"


# Task types the metering endpoints know how to filter/breakdown by — the same
# set service_breakdown() and build_task_type_selector() key off of. Anything
# outside this set can never match a real service, so letting it through used
# to silently produce an empty result set (200 OK, service_breakdown: []) instead
# of telling the caller their filter was wrong.
_VALID_TASK_TYPES = frozenset(SERVICE_BREAKDOWN_CONFIG)


def _parse_task_types(task_types: Optional[str]) -> Optional[list[str]]:
    """Parse the comma-separated ``task_types`` query param and validate each
    value against `_VALID_TASK_TYPES`.

    Raises 422 on any unsupported value (e.g. a typo like "a1c") instead of
    silently accepting it — matching the documented OpenAPI contract, same as
    WindowParam above.
    """
    if not task_types:
        return None
    values = [s.strip().lower() for s in task_types.split(",") if s.strip()]
    unknown = sorted(set(values) - _VALID_TASK_TYPES)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported task_types value(s): {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(_VALID_TASK_TYPES))}."
            ),
        )
    return values


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


def _partition_results(results: list) -> tuple[list, bool]:
    """Unwrap ``asyncio.gather(..., return_exceptions=True)`` results into
    (values-with-None-for-failures, degraded) — every route below downgrades
    a partial Prometheus/DB failure to a "degraded" response instead of a 500.
    """
    degraded = False
    values: list = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Metering query failed: %s", r)
            degraded = True
            values.append(None)
        else:
            values.append(r)
    return values, degraded


# ── Shared helpers ────────────────────────────────────────────────────────────


class _OrgLookupError(Exception):
    """Raised when the auth-DB lookup for a tenant's organisation fails —
    as opposed to a clean query finding no such tenant, which is a plain
    ``None`` return. Lets the caller tell "unknown tenant" (404) apart from
    "couldn't check right now" (503)."""


async def _resolve_org(svc: MeteringService, tenant_id: str) -> Optional[str]:
    if svc._auth_db is None or not tenant_id:
        return None
    try:
        row = await svc._auth_db.execute(
            text("SELECT organisation FROM tenants WHERE id = :id"),
            {"id": int(tenant_id)},
        )
        return row.scalar()
    except Exception as exc:
        logger.warning("Auth DB lookup failed for tenant_id=%s: %s", tenant_id, exc)
        raise _OrgLookupError(f"Auth DB lookup failed for tenant_id={tenant_id}") from exc


async def _resolve_tenant_scope(
    request: Request,
    svc: MeteringService,
    tenant_id: Optional[int],
    is_admin: bool,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve (scope_tenant id, scope_tenant_name) and enforce the tenant
    scoping guard on the NAME — the value PromQL selectors actually filter on,
    not the id in scope_tenant. Checking the guard on the id while querying by
    name let a missing/unresolved name fall through to an unscoped,
    platform-wide query.

    Non-admins are scoped to their own tenant via the gateway-injected
    X-Tenant-Name header. An admin may narrow to another tenant_id; when that
    id's organisation can't be resolved (unknown tenant / DB error), raise
    rather than silently widening the query to platform-wide.
    """
    caller_tid = _caller_tenant_id(request)
    scope_tenant = _validate_scope_tenant(caller_tid if not is_admin else (tenant_id or None))

    if not is_admin:
        scope_tenant_name = _caller_tenant_name(request)
    elif scope_tenant:
        try:
            scope_tenant_name = await _resolve_org(svc, scope_tenant)
        except _OrgLookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not verify the requested tenant right now; please retry.",
            ) from exc
        if scope_tenant_name is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not resolve organisation for tenant_id={scope_tenant}.",
            )
    else:
        scope_tenant_name = None

    # Security backstop: a tenant admin (role 5) MUST carry a tenant context —
    # the gateway injects X-Tenant-Name from the JWT-resolved tenant. Without
    # it, scope_tenant_name is None and the queries below would run unscoped,
    # leaking platform-wide aggregates. Refuse rather than widen scope
    # (defense-in-depth; the gateway should never let this through, but the
    # backstop guarantees it).
    if not is_admin and scope_tenant_name is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin requires a tenant context (X-Tenant-Name).",
        )

    return scope_tenant, scope_tenant_name


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


def _avg_requests_per_tenant_cell(
    ranking: Optional[dict], prev_avg: Optional[float]
) -> Optional[Cell]:
    """KPI card shown above the tenant ranking: avg requests per active
    tenant, with the vs-previous-window percentage change."""
    if not (ranking and ranking.get("total_tenant_count")):
        return None
    cur_avg = ranking.get("avg_per_active_tenant")
    pct = (
        round((cur_avg - prev_avg) / prev_avg * 100, 1)
        if (prev_avg and cur_avg is not None) else None
    )
    return Cell(
        key="avg_requests_per_tenant",
        label="Avg Requests Per Active Tenant",
        value=ranking["formatted_avg_per_active_tenant"],
        pct_change=pct,
    )


def _overview_kpis(rt: Optional[dict]) -> list[Cell]:
    """Successful/Failed show the COUNT as the value and the rate as
    sub-text (helper); both are colored on the frontend (green / red)."""
    if not rt:
        return []
    success_rate = rt["success_rate"]["rate_pct"]
    # No traffic → 0% failure (not 100%); 100−0 would be wrong.
    failure_rate = round(100 - success_rate, 2) if rt["total_requests"]["count"] else 0.0
    return [
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
    ]


def _platform_adoption_block(
    is_admin: bool,
    tc: Optional[dict],
    at24: Optional[dict],
    at7: Optional[dict],
    at30: Optional[dict],
    model_usage_growth_pct: Optional[float] = None,
) -> Optional[PlatformAdoption]:
    if not (is_admin and tc):
        return None
    return PlatformAdoption(
        total_tenants=tc["total_tenants"],
        new_tenants_15d=tc["new_tenants"],
        active_24h=at24["count"] if at24 else None,
        active_7d=at7["count"] if at7 else None,
        active_30d=at30["count"] if at30 else None,
        model_usage_growth_pct=model_usage_growth_pct,
    )


def _usage_concentration_block(is_admin: bool, conc: Optional[dict]) -> Optional[UsageConcentration]:
    """``tenant`` is resolved via _resolve_tenant_names (DB lookup, falling
    back to the raw Prometheus label only on a miss) — see
    MeteringService.usage_concentration."""
    if not (is_admin and conc):
        return None
    return UsageConcentration(
        top_tenants=[
            TenantRow(
                rank=t["rank"],
                tenant=t["tenant"],
                organisation=t["tenant"],
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


def _tenant_ranking_rows(ranking_tenants: list[dict]) -> list[TenantRow]:
    return [
        TenantRow(
            rank=t["rank"],
            tenant=t["tenant"],
            organisation=t["tenant"],
            requests=t["requests"],
            formatted_requests=t["formatted_requests"],
            percentage=t["percentage"],
        )
        for t in ranking_tenants
    ]


def _service_consumption_summary(breakdown: Optional[dict]) -> Optional[ServiceSummary]:
    """Summary KPIs — computed over services with traffic (a 0-request
    service must not win "highest failure rate")."""
    if breakdown is None:
        return None
    active = [s for s in breakdown["services"] if s["requests"] > 0]
    most_used = max(active, key=lambda s: s["requests"]) if active else None
    worst = max(active, key=lambda s: 100 - s["success_pct"]) if active else None
    return ServiceSummary(
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


def _model_consumption_summary(
    breakdown: Optional[dict], total_models: Optional[int], most_used: Optional[dict],
) -> Optional[ModelConsumptionSummary]:
    """Model Consumption KPI cards (AI4IDS-2790) — active_models/overall_success_rate_pct/
    worst all computed in one pass by MeteringService.model_consumption_kpis; `most_used`
    is model-level (pre-aggregated by MeteringService.model_consumption_ranking),
    `highest_failure_rate` stays service-level."""
    if breakdown is None:
        return None
    kpis = MeteringService.model_consumption_kpis(breakdown["services"], breakdown["model_totals"])
    worst = kpis["worst"]

    return ModelConsumptionSummary(
        total_models=total_models,
        active_models=kpis["active_models"],
        overall_success_rate_pct=kpis["overall_success_rate_pct"],
        most_used=(
            MostUsedModel(
                model_id=most_used["model_id"], name=most_used["model_name"], requests=most_used["requests"]
            )
            if most_used else None
        ),
        highest_failure_rate=(
            HighestFailureModel(
                service_id=worst["service_id"],
                name=worst["name"],
                failure_rate_pct=round(100 - worst["success_pct"], 2),
            )
            if worst else None
        ),
    )


_STEP_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _step_seconds(step: str) -> int:
    """Parse a Prometheus duration step (e.g. '10m', '4h', '1d') to seconds."""
    m = re.fullmatch(r"(\d+)([smhd])", step.strip())
    return int(m.group(1)) * _STEP_UNIT_SECONDS[m.group(2)] if m else 0


async def _request_volume_chart(
    svc: MeteringService,
    window: str,
    tenant: Optional[str],
    task_types: Optional[list[str]] = None,
    tenant_id: Optional[str] = None,
    auth_type: Optional[str] = None,
) -> Optional[Graph]:
    """OVERVIEW "Request Volume" chart — successful vs failed request COUNTS per bucket:
      - "successful" : 2xx request count per bucket
      - "failed"     : 4xx/5xx request count per bucket
    """
    if window not in WINDOW_STEP:
        return None
    from app.utils.metering_promql_builder import (
        build_base_selectors, build_task_type_selector, sum_over_window,
    )

    task_sel = build_task_type_selector(task_types)
    success_extra = [task_sel, 'status_code=~"2.."'] if task_sel else ['status_code=~"2.."']
    failed_extra = [task_sel, 'status_code=~"[45].."'] if task_sel else ['status_code=~"[45].."']
    success_sel = build_base_selectors(
        inference_only=True, tenant=tenant, extra=success_extra, tenant_id=tenant_id, auth_type=auth_type
    )
    failed_sel = build_base_selectors(
        inference_only=True, tenant=tenant, extra=failed_extra, tenant_id=tenant_id, auth_type=auth_type
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
    success_q = f"{sum_over_window(success_metric, step)} or vector(0)"
    failed_q  = f"{sum_over_window(failed_metric,  step)} or vector(0)"

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


# Allowed time windows, typed as a Literal so FastAPI validates the query param
# itself and returns the standard 422 for unsupported values (e.g. "15d") — matching
# the documented OpenAPI contract — instead of a hand-rolled 400. ("all" is internal
# only and intentionally not an accepted window for these dashboard endpoints.)
WindowParam = Literal["1h", "24h", "7d", "30d"]


# ── Tab 1: Overview ───────────────────────────────────────────────────────────


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    request: Request,
    window: WindowParam = Query("24h", description="Time window: 1h | 24h | 7d | 30d"),
    limit: int = Query(10, ge=1, le=50, description="Max tenants in usage concentration ranking"),
    tenant_id: Optional[int] = Query(None, ge=1, description="Narrow to a specific tenant (admin only)"),
    task_types: Optional[str] = Query(
        None, description="Comma-separated task types to scope KPIs, the request-volume "
        "chart, and usage concentration to (e.g. llm,nmt). Unsupported values are "
        "rejected with 422."
    ),
    svc: MeteringService = Depends(get_metering_service),
    redis: aioredis.Redis = Depends(get_redis),
):
    _require_metering_access(request)

    is_admin = _is_platform_admin(request)
    scope_tenant, scope_tenant_name = await _resolve_tenant_scope(request, svc, tenant_id, is_admin)
    task_type_filter = _parse_task_types(task_types)
    # UI/playground calls are free — restrict the request-count KPI and the
    # request-volume chart to API-key-authenticated traffic only, same as
    # payperuse_consumer/handler.py already restricts billing.
    auth_type_filter = API_KEY_AUTH_TYPE

    ranking_active = is_admin and not scope_tenant
    cache_key = (
        f"metering:overview:v2:{window}:{scope_tenant_name or 'all'}:"
        f"{_caller_role_label(request)}:{','.join(task_type_filter) if task_type_filter else 'all'}"
        + (f":{limit}" if ranking_active else "")
    )
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    # tenant_count()/active_tenants() all touch self._auth_db (a single
    # AsyncSession — NOT safe for concurrent use), so they're fetched via
    # overview_tenant_data() rather than being thrown into the same gather()
    # as everything else below — see its docstring for the concurrency bug
    # that caused (sqlalchemy.exc.InvalidRequestError: "This session is
    # provisioning a new connection").
    tc, active_by_range = await svc.overview_tenant_data(["24h", "7d", "30d"])

    results = await asyncio.gather(
        svc.request_total(
            inference_only=True, tenant=scope_tenant_name, service_id=None, time_range=window,
            task_types=task_type_filter, tenant_id=scope_tenant, auth_type=auth_type_filter,
        ),
        _request_volume_chart(
            svc, window, scope_tenant_name, task_type_filter,
            tenant_id=scope_tenant, auth_type=auth_type_filter,
        ),
        # Usage Concentration is platform-wide; hide it when a tenant filter is applied.
        svc.usage_concentration(limit=limit, time_range=window, task_types=task_type_filter)
        if ranking_active else asyncio.sleep(0),
        # Key Metrics KPI #7 (model_usage_growth_pct) is admin-only, fixed
        # calendar-month comparison — independent of `window`.
        svc.model_usage_growth_pct() if is_admin else asyncio.sleep(0),
        return_exceptions=True,
    )
    # Merge both result sets through one _partition_results call so a failure
    # in either half still degrades the response instead of raising —
    # active_tenants() (unlike tenant_count()) doesn't catch a Prometheus
    # query failure internally, so its slot here can be a real Exception.
    combined, degraded = _partition_results([
        active_by_range["24h"], active_by_range["7d"], active_by_range["30d"], *results,
    ])
    at24, at7, at30, rt, chart, conc, model_usage_growth_pct = combined

    org = scope_tenant_name

    kpis = _overview_kpis(rt)
    # Platform adoption / usage concentration are admin-only blocks.
    platform_adoption = _platform_adoption_block(is_admin, tc, at24, at7, at30, model_usage_growth_pct)
    usage_conc = _usage_concentration_block(is_admin, conc)

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = OverviewResponse(
        scope=Scope(
            role=_caller_role_label(request), tenant_id=scope_tenant, organisation=org,
            window=window, task_types=task_type_filter,
        ),
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
    window: WindowParam = Query("24h", description="Time window: 1h | 24h | 7d | 30d"),
    limit: int = Query(10, ge=1, le=50, description="Max tenants to return"),
    tenant_id: Optional[int] = Query(None, ge=1, description="Scope to a single tenant (admin only)"),
    task_types: Optional[str] = Query(
        None,
        description="Comma-separated task types for the heatmap columns (default: all). "
        "Unsupported values are rejected with 422.",
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

    # Admin-only endpoint: scope to the selected tenant when one is chosen,
    # otherwise platform-wide (tenant=None) for the cross-tenant ranking.
    # Routed through _resolve_tenant_scope (is_admin=True) so an unresolvable
    # tenant_id raises rather than silently falling through to a platform-wide
    # query that Scope.tenant_id would still report as tenant-scoped.
    scope_tenant, scope_tenant_name = await _resolve_tenant_scope(request, svc, tenant_id, True)

    task_type_filter = _parse_task_types(task_types)

    cache_key = (
        f"metering:tenant-consumption:v2:{window}:{limit}:{scope_tenant_name or 'all'}:"
        f"{','.join(task_type_filter) if task_type_filter else 'all'}"
    )
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    async def _ranking_then_heatmap():
        """tenant_ranking and usage_by_tenant_service both now resolve
        tenant names via self._auth_db (_resolve_tenant_names) — a single
        AsyncSession, not safe for concurrent use (see overview_tenant_data's
        docstring for the exact InvalidRequestError this avoids). Unlike
        that error, _resolve_tenant_names swallows the failure and falls
        back to the raw Prometheus tenant label — silently showing the
        stale pre-rename name on whichever call loses the race. So these
        two must run sequentially relative to EACH OTHER; each still
        degrades independently (mirrors _partition_results' per-item
        contract) rather than one failure taking both down.
        """
        try:
            ranking_result = await svc.tenant_ranking(
                limit=limit, time_range=window, tenant=scope_tenant_name, tenant_id=scope_tenant,
            )
        except Exception as exc:
            ranking_result = exc
        try:
            heatmap_result = await svc.usage_by_tenant_service(
                limit=limit, time_range=window, services=task_type_filter,
                tenant=scope_tenant_name, tenant_id=scope_tenant,
            )
        except Exception as exc:
            heatmap_result = exc
        return ranking_result, heatmap_result

    (ranking, heatmap), prev_avg = await asyncio.gather(
        _ranking_then_heatmap(),
        svc.avg_per_active_tenant_previous(window, tenant=scope_tenant_name, tenant_id=scope_tenant),
    )
    (ranking, heatmap, prev_avg), degraded = _partition_results([ranking, heatmap, prev_avg])

    ranking_tenants = ranking["tenants"] if ranking else []
    heatmap_rows = heatmap["tenants"] if heatmap else []

    # ``tenant`` is resolved via _resolve_tenant_names (DB lookup, falling
    # back to the raw Prometheus label only on a miss) — see
    # usage_by_tenant_service — so this is NOT always already the
    # organisation name; it's just already the best display value available.
    for r in heatmap_rows:
        r["organisation"] = r["tenant"]

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = TenantConsumptionResponse(
        scope=Scope(
            role=_caller_role_label(request),
            tenant_id=scope_tenant,
            organisation=scope_tenant_name,
            window=window,
            task_types=task_type_filter,
        ),
        avg_requests_per_tenant=_avg_requests_per_tenant_cell(ranking, prev_avg),
        tenant_ranking=_tenant_ranking_rows(ranking_tenants),
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
    window: WindowParam = Query("24h", description="Time window: 1h | 24h | 7d | 30d"),
    tenant_id: Optional[int] = Query(None, ge=1, description="Narrow to a specific tenant (admin only)"),
    task_types: Optional[str] = Query(
        None, description="Comma-separated task types to include (frontend allowlist). "
        "Unsupported values are rejected with 422."
    ),
    svc: MeteringService = Depends(get_metering_service),
    redis: aioredis.Redis = Depends(get_redis),
):
    _require_metering_access(request)

    is_admin = _is_platform_admin(request)
    scope_tenant, scope_tenant_name = await _resolve_tenant_scope(request, svc, tenant_id, is_admin)
    task_type_filter = _parse_task_types(task_types)

    cache_key = (
        f"metering:service-consumption:v2:{window}:{scope_tenant_name or 'all'}:"
        f"{','.join(task_type_filter) if task_type_filter else 'all'}:{_caller_role_label(request)}"
    )
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    results = await asyncio.gather(
        svc.service_breakdown(
            tenant=scope_tenant_name, time_range=window, service_filter=task_type_filter,
            tenant_id=scope_tenant,
        ),
        return_exceptions=True,
    )
    (breakdown,), degraded = _partition_results(results)

    org = scope_tenant_name

    services = breakdown["services"] if breakdown else []
    summary = _service_consumption_summary(breakdown)

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = ServiceConsumptionResponse(
        scope=Scope(
            role=_caller_role_label(request), tenant_id=scope_tenant, organisation=org,
            window=window, task_types=task_type_filter,
        ),
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


# ── Tab 4: Model Consumption ──────────────────────────────────────────────────


@router.get("/model-consumption", response_model=ModelConsumptionResponse)
async def get_model_consumption(
    request: Request,
    window: WindowParam = Query("24h", description="Time window: 1h | 24h | 7d | 30d"),
    tenant_id: Optional[int] = Query(None, ge=1, description="Narrow to a specific tenant (admin only)"),
    limit: int = Query(10, ge=1, le=25, description="Max models to return in top_models"),
    svc: MeteringService = Depends(get_metering_service),
    redis: aioredis.Redis = Depends(get_redis),
):
    _require_metering_access(request)

    is_admin = _is_platform_admin(request)
    scope_tenant, scope_tenant_name = await _resolve_tenant_scope(request, svc, tenant_id, is_admin)

    # v3: TopModelRow/ServiceModelRow gained a required `model_id` field.
    # Bumped from v2 so a payload cached just before this deploy (with no
    # model_id) can't be served back and fail ModelConsumptionResponse
    # validation with a 500 for up to the 60s TTL — it starts from a cold key.
    cache_key = (
        f"metering:model-consumption:v3:{window}:{limit}:{scope_tenant_name or 'all'}:"
        f"{_caller_role_label(request)}"
    )
    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    results = await asyncio.gather(
        svc.model_breakdown(tenant=scope_tenant_name, time_range=window, tenant_id=scope_tenant),
        return_exceptions=True,
    )
    (breakdown,), degraded = _partition_results(results)
    # Not gathered with model_breakdown above: both end up querying the same
    # per-request AsyncSession (ServiceRepository(db) / ModelRepository(db) in
    # get_metering_service share `db`), and AsyncSession is not safe for
    # concurrent use — see the same note on tenant_count(). registry_model_count()
    # never raises (catches internally), so it can't regress `degraded`.
    total_models = await svc.registry_model_count()

    org = scope_tenant_name

    services = breakdown["services"] if breakdown else []
    model_totals = breakdown["model_totals"] if breakdown else []
    # most_used/top_models rank model_breakdown's already-grouped, Registry-
    # validated model_totals — see MeteringService.model_consumption_ranking.
    # top_models_total_requests is the model-level denominator
    # consumption_pct is computed against — NOT the full window's total.
    most_used, ranked_models, top_models_total_requests = (
        svc.model_consumption_ranking(model_totals, limit) if breakdown is not None else (None, [], 0)
    )
    summary = _model_consumption_summary(breakdown, total_models, most_used)
    top_models = [TopModelRow(**m) for m in ranked_models]

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = ModelConsumptionResponse(
        scope=Scope(role=_caller_role_label(request), tenant_id=scope_tenant, organisation=org, window=window),
        summary=summary,
        top_models=top_models,
        top_models_total_requests=top_models_total_requests,
        breakdown=[
            ServiceModelRow(
                service_id=s["service_id"],
                name=s["name"],
                model_id=s["model_id"],
                model_name=s["model_name"],
                requests=s["requests"],
                native_units=s["native_units"],
                native_unit_suffix="tokens",
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
