"""Usage Dashboard metering from usage_events / daily_usage instead of
Prometheus (METERING_DATA_SOURCE=usage_events).

Serves everything the Overview and Model consumption tabs read: request,
success and failure counts, average RPS, the request-volume chart, usage
concentration, active institutions and models, model usage growth, first
usage, and the per-model requests, success % and native units (with the LLM
token split). The counts come from request rows and the units from usage rows
(see MeteringUsageRepository), so figures are exact rather than Prometheus'
extrapolated increase(), and not limited by its retention: days past
usage_events' own retention come from the daily_usage rollup, by the day.

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
from typing import Callable, Optional, Union

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
from app.utils.usage_period import IST, ist_midnight

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


def _seconds(start: datetime, end: datetime) -> int:
    return max(1, round((end - start).total_seconds()))


def _use_previous_of(result: dict, versus: dict) -> None:
    """Take request_total's vs-previous figures from ``versus`` (the
    whole-day comparison), keeping the counts shown."""
    for key, shown in result.items():
        if key != "filters":
            shown.update({k: v for k, v in versus[key].items() if "previous" in k})


def _fallback_figures(
    fmt: Callable[[int], str], cur: UsageAgg, compared: Optional[UsageAgg], prev_fb: Optional[UsageAgg],
) -> dict:
    """request_total's fallback_requests: ``cur``'s counts, the vs-previous
    % of ``compared`` against ``prev_fb`` (None without it)."""
    def figure(attr: str) -> dict:
        current = getattr(cur, attr)
        previous = getattr(prev_fb, attr) if prev_fb is not None else None
        against = getattr(compared, attr) if compared is not None else current
        return {
            "count": current,
            "formatted": fmt(current),
            "vs_previous_pct": round((against - previous) / previous * 100, 1) if previous else None,
            "previous_count": previous,
            "previous_formatted": fmt(previous) if previous is not None else None,
        }

    return {**figure("fallback"), "successful": figure("fallback_successful"), "failed": figure("fallback_failed")}


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
        """No retention to refresh: days past usage_events' retention are read
        from daily_usage (see MeteringUsageRepository)."""

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
        as Prometheus reported them past its retention.

        When the previous span ends partway through a day whose usage_events
        rows were dropped (last 7 days' previous span ends 7 days back at
        this hour), that day's part can't be counted, and the span would come
        up short and inflate the growth %. Both spans are then compared over
        their whole days only (up to today's midnight, and the same shifted
        back), all of them in daily_usage; the counts shown still cover the
        whole range, only the vs-previous figures leave today's part out.

        Also fallback_requests: the requests sent to a fallback service,
        already part of the total (0 when there were none), with how many of
        them succeeded and failed (status 400 or above). Only this store
        records fallbacks, so the other backends leave the key out. Its
        previous figures are None too when that span starts before fallbacks
        were recorded."""
        start, end, shift = self._bounds(time_range)
        tid, type_ids = _tenant_pk(tenant_id, tenant), await self._type_ids(task_types)
        seconds = _seconds(start, end)
        cur = await self._counts(start, end, tid, type_ids)
        prev_start, prev_end = start - timedelta(seconds=shift), end - timedelta(seconds=shift)
        prev_end, compared, compared_seconds = await self._compared_span(
            start, prev_start, prev_end, shift, cur, tid, type_ids,
        )
        prev, prev_fb = await self._previous_counts(prev_start, prev_end, compared, tid, type_ids)
        previous = (prev.requests, prev.successful, prev.requests / compared_seconds) if prev is not None else None
        filters = {
            "inference_only": inference_only, "tenant": tenant,
            "service_id": service_id, "time_range": time_range or "all",
        }
        result = request_total_result(
            cur.requests, cur.successful, round(cur.requests / seconds, 4), previous, filters=filters,
        )
        if compared is not cur and previous is not None:
            _use_previous_of(result, request_total_result(
                compared.requests, compared.successful, round(compared.requests / compared_seconds, 4),
                previous, filters=filters,
            ))
        result["fallback_requests"] = _fallback_figures(self._format_count, cur, compared, prev_fb)
        return result

    async def _compared_span(
        self, start: datetime, prev_start: datetime, prev_end: datetime, shift: int,
        cur: UsageAgg, tid: Optional[int], type_ids: Optional[list[int]],
    ) -> tuple[datetime, Optional[UsageAgg], int]:
        """(previous span's end, what it's compared with, that span's seconds)
        for request_total: the current span as is, or — when the previous one
        ends mid a dropped day — both cut to whole days (see request_total).
        None to compare with when no whole day is left."""
        if not await self._usage.ends_mid_dropped_day(prev_end):
            return prev_end, cur, _seconds(start, prev_end + timedelta(seconds=shift))
        prev_end = ist_midnight(prev_end.astimezone(IST).date())
        if prev_end <= prev_start:
            return prev_end, None, 1
        compared_end = prev_end + timedelta(seconds=shift)
        return prev_end, await self._counts(start, compared_end, tid, type_ids), _seconds(start, compared_end)

    async def _previous_counts(
        self, prev_start: datetime, prev_end: datetime, compared: Optional[UsageAgg],
        tid: Optional[int], type_ids: Optional[list[int]],
    ) -> tuple[Optional[UsageAgg], Optional[UsageAgg]]:
        """(previous span's counts, the same for its fallback figures): None
        when there's nothing to compare with, or request rows don't cover the
        span; fallbacks None too when it starts before they were recorded."""
        if compared is None or not await self._covered(prev_start, prev_end):
            return None, None
        prev = await self._counts(prev_start, prev_end, tid, type_ids)
        return prev, (prev if await self._usage.fallbacks_recorded_by(prev_start) else None)

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
        """LLM requests, the last 30 whole IST days (up to today's midnight)
        vs the 30 before. Whole days: windows ending now would start and end
        partway through days whose usage_events rows were dropped, which
        can't be cut at the hour (see MeteringUsageRepository), so the two
        would count different lengths. None until request rows cover the
        whole 60 days, or with no traffic in the earlier 30."""
        today = ist_midnight(datetime.now(IST).date())
        month = timedelta(days=30)
        if not await self._covered(today - 2 * month, today):
            return None
        type_ids = await self._type_ids(["llm"])
        cur = await self._counts(today - month, today, None, type_ids)
        prev = await self._counts(today - 2 * month, today - month, None, type_ids)
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
