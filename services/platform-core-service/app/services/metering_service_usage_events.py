"""Usage Dashboard metering from usage_events / daily_usage instead of
Prometheus (METERING_DATA_SOURCE=usage_events).

Serves everything the Overview and Model consumption tabs read: request,
success and failure counts, average RPS, the request-volume chart, usage
concentration, active institutions and models, model usage growth, first
usage, and the per-model requests, success % and native units (with the LLM
token split). The counts come from request rows and the units from usage rows
(see MeteringUsageRepository), so figures are exact rather than Prometheus'
extrapolated increase(), and not limited by its retention.

Only API-key traffic is recorded, which is what the dashboard already counted.
Request rows exist from the cut-over onwards; data_since() reports when they
begin, so an earlier range is flagged partial instead of shown incomplete.

The rest of MeteringService (registry model counts, tenant names, the
per-model shaping) is inherited unchanged. The Prometheus client is kept
only for the /tenant-consumption tab, which isn't part of the dashboard.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.model_management.model_repository import ModelRepository
from app.repositories.model_management.service_repository import ServiceRepository
from app.repositories.pay_per_use.metering_usage import MeteringUsageRepository, UsageAgg
from app.schemas.metering import Graph, GraphPoint, GraphSeries
from app.services.metering_service import (
    _UNSET,
    _WINDOW_SECONDS,
    LLM_TOKEN_ENTRIES,
    MeteringService,
    _llm_token_key,
    _range_chart_buckets,
    _step_seconds,
    request_total_result,
)
from app.services.pay_per_use import inference_type_cache
from app.utils.metering_promql_builder import (
    PROMETHEUS_API_PATH_LABEL,
    AbsoluteRange,
    TimeRange,
    comparison_shift_seconds,
)
from app.utils.prometheus_client import PrometheusClient
from app.utils.usage_period import IST

logger = logging.getLogger(__name__)

_DAY_SECONDS = 86_400


def _tenant_pk(tenant_id, tenant: Optional[str] = None) -> Optional[int]:
    """The tenant filter for a query: the id as an int, or None for no filter
    (platform-wide). Fails closed: a scope that names a tenant but carries no
    usable id raises instead of reading as "no filter" — these queries filter
    on the id only, so dropping it would widen a tenant's view to every
    tenant's totals."""
    if tenant_id is not None and str(tenant_id).isdigit():
        return int(tenant_id)
    if tenant_id is not None or tenant:
        raise PermissionError(f"tenant scope without a usable tenant id (tenant_id={tenant_id!r})")
    return None


class UsageEventsMeteringService(MeteringService):
    def __init__(
        self,
        db: AsyncSession,
        client: Optional[PrometheusClient] = None,
        auth_db: Optional[AsyncSession] = None,
        service_repo: Optional[ServiceRepository] = None,
        model_repo: Optional[ModelRepository] = None,
    ) -> None:
        super().__init__(client, auth_db, service_repo, model_repo)
        self._db = db
        self._usage = MeteringUsageRepository(db)
        self._types: Optional[dict[int, tuple[str, str]]] = None
        self._units: dict[str, str] = {}

    # ── Store plumbing ────────────────────────────────────────────────────────

    async def refresh_retention(self) -> None:
        """No retention to refresh: usage_events keeps every day."""

    async def data_since(self, period) -> Optional[datetime]:
        """When request rows begin inside the period: its start once they
        cover it, the first one when they start inside it, None when there
        are none — so a range from before the cut-over is reported partial."""
        return await self._usage.request_rows_from(period.start, period.end)

    @staticmethod
    def _bounds(time_range: TimeRange) -> tuple[datetime, datetime, int]:
        """(start, end, vs-previous shift in seconds) for an AbsoluteRange or a
        preset key ("24h", "30d" …), the preset ending now."""
        if isinstance(time_range, AbsoluteRange):
            return time_range.start, time_range.end, comparison_shift_seconds(time_range)
        seconds = _WINDOW_SECONDS.get(time_range or "")
        if seconds is None:
            raise ValueError(f"unsupported time range for usage_events metering: {time_range!r}")
        end = datetime.now(timezone.utc)
        return end - timedelta(seconds=seconds), end, seconds

    async def _catalogue(self) -> dict[int, tuple[str, str]]:
        """{inference_type_id: (metering task key, endpoint)}: the task key
        the dashboard filters and labels by (e.g. "audio_language_detection"),
        resolved from the type's endpoint the way Prometheus' endpoint label
        was, and that endpoint for _shape_model_breakdown's rows."""
        if self._types is None:
            async with self._usage.lock:   # may fall back to the shared core-DB session
                entries = await inference_type_cache.get_all(self._db)
            types = {}
            self._units = {entry["name"]: entry["unit"] for entry in entries}
            for entry in entries:
                endpoint = (entry.get("endpoint_patterns") or [""])[0]
                task = self._resolve_task_key(endpoint) or str(entry.get("name", "")).replace("-", "_")
                types[int(entry["id"])] = (task, endpoint)
            self._types = types
        return self._types

    async def _type_ids(self, task_types: Optional[list[str]]) -> Optional[list[int]]:
        """Catalogue ids for the dashboard's task keys; None = every type."""
        if not task_types:
            return None
        wanted = set(task_types)
        return [type_id for type_id, (task, _) in (await self._catalogue()).items() if task in wanted]

    async def _counts(self, start, end, tenant_id, type_ids) -> UsageAgg:
        rows = await self._usage.aggregate(start, end, (), tenant_id=tenant_id, type_ids=type_ids)
        return rows.get((), UsageAgg())

    async def _covered(self, start: datetime, end: datetime) -> bool:
        """Request rows cover [start, end) from its start."""
        return await self._usage.request_rows_from(start, end) == start

    # ── Overview ──────────────────────────────────────────────────────────────

    async def request_total(
        self,
        inference_only: bool,
        tenant: Optional[str],
        service_id: Optional[str],
        time_range: TimeRange,
        task_types: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
        auth_type: Optional[str] = None,
    ) -> dict:
        """Total / successful / failed requests and average RPS, against the
        same span shifted back (for `today`, yesterday's same clock span).
        The previous figures are None when request rows don't cover that span,
        as Prometheus reported them past its retention."""
        start, end, shift = self._bounds(time_range)
        tid, type_ids = _tenant_pk(tenant_id, tenant), await self._type_ids(task_types)
        seconds = max(1, round((end - start).total_seconds()))
        cur = await self._counts(start, end, tid, type_ids)
        prev_start, prev_end = start - timedelta(seconds=shift), end - timedelta(seconds=shift)
        previous = None
        if await self._covered(prev_start, prev_end):
            prev = await self._counts(prev_start, prev_end, tid, type_ids)
            previous = (prev.requests, prev.successful, prev.requests / seconds)
        return request_total_result(
            cur.requests, cur.successful, round(cur.requests / seconds, 4), previous,
            filters={
                "inference_only": inference_only, "tenant": tenant,
                "service_id": service_id, "time_range": time_range or "all",
            },
        )

    async def request_volume_chart(
        self,
        window: Union[str, AbsoluteRange],
        tenant: Optional[str],
        task_types: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
        auth_type: Optional[str] = None,
    ) -> Optional[Graph]:
        """Successful and failed requests per bucket, anchored at the range's
        start like the Prometheus chart (its last bucket partial when the
        range isn't whole steps), each point at its bucket's start. Hourly
        buckets read usage_events; daily and weekly ones sum IST days, from
        daily_usage where it has them. Empty buckets are 0, so the timeline
        is continuous."""
        if not isinstance(window, AbsoluteRange):
            start, end, _ = self._bounds(window)
            window = AbsoluteRange(start=start, end=end)
        step, n_full, tail = _range_chart_buckets(window)
        step_secs = _step_seconds(step)
        n_buckets = n_full + (1 if tail else 0)
        tid, type_ids = _tenant_pk(tenant_id, tenant), await self._type_ids(task_types)

        succ = [0] * n_buckets
        fail = [0] * n_buckets
        if step_secs < _DAY_SECONDS:
            buckets = await self._usage.request_buckets(
                window.start, window.end, step_secs, tenant_id=tid, type_ids=type_ids,
            )
            for index, (requests, failed) in buckets.items():
                if 0 <= index < n_buckets:
                    succ[index] += requests - failed
                    fail[index] += failed
        else:
            by_day = await self._usage.aggregate(
                window.start, window.end, ("day",), tenant_id=tid, type_ids=type_ids,
            )
            for (day,), agg in by_day.items():
                # The bucket holding the day's IST midnight.
                offset = (datetime.combine(day, time(), tzinfo=IST) - window.start).total_seconds()
                index = min(n_buckets - 1, max(0, int(offset // step_secs)))
                succ[index] += agg.successful
                fail[index] += agg.failed

        if not any(succ) and not any(fail):
            return None
        start_ts = window.start.timestamp()
        stamps = [int(start_ts + i * step_secs) for i in range(n_full)]
        if tail:
            stamps.append(int((window.end - timedelta(seconds=tail)).timestamp()))
        return Graph(
            step=step,
            series=[
                GraphSeries(key="successful", label="Successful",
                            points=[GraphPoint(ts=t, value=float(v)) for t, v in zip(stamps, succ)]),
                GraphSeries(key="failed", label="Failed",
                            points=[GraphPoint(ts=t, value=float(v)) for t, v in zip(stamps, fail)]),
            ],
        )

    async def active_tenants(
        self, time_range: Optional[str], valid_names: Union[set, None, object] = _UNSET,
    ) -> dict:
        """Institutions with at least one request in the window, limited to
        currently-ACTIVE ones (valid_names; None = auth DB unavailable, no
        filter). Names resolved only for a standalone call, as in the
        Prometheus version."""
        start, end, _ = self._bounds(time_range)
        rows = await self._usage.aggregate(start, end, ("tenant_id",))
        resolve_names = valid_names is _UNSET
        if valid_names is _UNSET:
            valid_names = await self._fetch_valid_tenant_ids()
        counts = {
            str(tid): agg.requests for (tid,), agg in rows.items()
            if tid is not None and agg.requests > 0
            and (valid_names is None or str(tid) in valid_names)
        }
        names = await self._resolve_tenant_names(set(counts)) if resolve_names else {}
        tenants = [
            {"tenant": names.get(tid, "") or tid, "request_count": count}
            for tid, count in counts.items()
        ]
        return {
            "active_tenants": tenants,
            "count": len(tenants),
            "filters": {"time_range": time_range or "all"},
        }

    async def overview_tenant_data(self, time_ranges: list[str]) -> tuple[dict, dict[str, dict]]:
        """As MeteringService.overview_tenant_data, but the per-window counts
        run one after another: they read the shared core-DB session."""
        tc = await self.tenant_count()
        valid_names = await self._fetch_valid_tenant_ids()
        active = {}
        for time_range in time_ranges:
            try:
                active[time_range] = await self.active_tenants(time_range, valid_names=valid_names)
            except Exception as exc:   # degraded, as a failed Prometheus query was
                active[time_range] = exc
        return tc, active

    async def usage_concentration(
        self, limit: int, time_range: TimeRange, task_types: Optional[list[str]] = None,
    ) -> dict:
        """Requests per institution, the top ``limit`` and the rest."""
        start, end, _ = self._bounds(time_range)
        rows = await self._usage.aggregate(
            start, end, ("tenant_id",), type_ids=await self._type_ids(task_types),
        )
        counts = {str(tid): agg.requests for (tid,), agg in rows.items() if tid is not None and agg.requests > 0}
        names = await self._resolve_tenant_names(set(counts))
        all_tenants = sorted(
            ({"tenant": names.get(tid, "") or tid, "requests": count} for tid, count in counts.items()),
            key=lambda t: t["requests"], reverse=True,
        )
        grand_total = sum(t["requests"] for t in all_tenants)
        top, rest = all_tenants[:limit], all_tenants[limit:]
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
        return {
            "top_tenants": top_tenants,
            "others": {
                "count": len(rest),
                "requests": others_requests,
                "percentage": round(others_requests / grand_total * 100, 1) if grand_total else 0.0,
            },
            "top_concentration_percentage": round(sum(t["percentage"] for t in top_tenants), 1),
            "grand_total": grand_total,
            "filters": {"limit": limit, "time_range": time_range or "all"},
        }

    async def model_usage_growth_pct(self) -> Optional[float]:
        """LLM requests, last 30 days vs the 30 before. None until request
        rows cover the whole 60 days, or with no traffic in the earlier 30."""
        now = datetime.now(timezone.utc)
        month = timedelta(days=30)
        if not await self._covered(now - 2 * month, now):
            return None
        type_ids = await self._type_ids(["llm"])
        cur = await self._counts(now - month, now, None, type_ids)
        prev = await self._counts(now - 2 * month, now - month, None, type_ids)
        if prev.requests <= 0:
            return None
        return round((cur.requests - prev.requests) / prev.requests * 100, 1)

    async def first_request_at(
        self, tenant: Optional[str], tenant_id: Optional[str] = None,
    ) -> Optional[datetime]:
        """When the institution's (all institutions' when none) API-key usage
        begins — one half of /overview's first_usage_at."""
        return await self._usage.first_usage(_tenant_pk(tenant_id, tenant))

    # ── Model consumption ─────────────────────────────────────────────────────

    async def model_breakdown(
        self, tenant: Optional[str], time_range: TimeRange,
        tenant_id: Optional[str] = None,
        task_types: Optional[list[str]] = None,
    ) -> dict:
        """Per-service and per-model requests, success % and native units
        (the LLM rows with their input / cached input / output split). Rows
        are reshaped into the Prometheus result shape so the inherited
        _shape_model_breakdown (registry validation, per-model rollup) runs
        unchanged, as the OpenSearch backend does. The task comes from each
        row's catalogue type; model_id from the service registry."""
        start, end, _ = self._bounds(time_range)
        catalogue = await self._catalogue()
        unit_map = self._units   # {catalogue name: unit}, from the same catalogue read
        rows = await self._usage.aggregate(
            start, end, ("service_id", "inference_type_id"),
            tenant_id=_tenant_pk(tenant_id, tenant), type_ids=await self._type_ids(task_types),
        )

        total_rows: list[dict] = []
        success_rows: list[dict] = []
        llm_keys = [_llm_token_key(t) for _, _, t in LLM_TOKEN_ENTRIES]   # prompt, cached, completion
        native_by_task: dict[str, dict[str, float]] = {key: {} for key in llm_keys}
        for (service_id, type_id), agg in rows.items():
            sid = service_id or ""
            task, endpoint = catalogue.get(type_id, (None, ""))
            metric = {"service_id": sid, "model_id": "", PROMETHEUS_API_PATH_LABEL: endpoint}
            total_rows.append({"metric": metric, "value": [0, agg.requests]})
            success_rows.append({"metric": metric, "value": [0, agg.successful]})
            if not task or not sid:
                continue
            by_service = native_by_task.setdefault(task, {})
            by_service[sid] = by_service.get(sid, 0.0) + float(agg.units)
            if task == "llm":
                # Billed LLM units are input + output tokens, input including
                # the cached ones — the prompt / cached / completion series.
                parts = (agg.units - agg.output_units, agg.cached_units, agg.output_units)
                for key, value in zip(llm_keys, parts):
                    native_by_task[key][sid] = native_by_task[key].get(sid, 0.0) + float(value)

        return await self._shape_model_breakdown(
            total_rows, success_rows, native_by_task, unit_map, tenant, time_range, task_types,
        )
