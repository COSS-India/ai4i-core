"""Metering business logic — PromQL construction, Prometheus calls, result shaping."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


from app.core.config import settings
from app.repositories.model_management.model_repository import ModelRepository
from app.repositories.model_management.service_repository import ServiceRepository
from app.utils.prometheus_client import PrometheusClient
from app.services.pay_per_use import inference_type_cache
from app.utils.metering_promql_builder import (
    TIME_RANGES,
    SERVICE_BREAKDOWN_CONFIG,
    SERVICE_BREAKDOWN_ENDPOINT_REGEX,
    LLM_CHAT_ENDPOINT_REGEX,
    ENDPOINT_TO_TASK,
    PROMETHEUS_API_PATH_LABEL,
    API_KEY_AUTH_TYPE,
    api_key_auth_type_selector,
    build_base_selectors,
    build_task_type_selector,
    escape_label_value,
    sum_over_window,
    sum_over_window_by,
)

logger = logging.getLogger(__name__)

_METRIC = "telemetry_obsv_requests_total"

# SERVICE_BREAKDOWN_CONFIG's task keys (underscore-separated, matching the
# metering module's own PromQL/endpoint conventions — see ENDPOINT_TO_TASK)
# are NOT always the same string mm_models.task["type"] stores in the DB.
# The Registry's canonical values come from TaskTypeEnum
# (app/schemas/enums/model_management.py), which uses hyphens for compound
# names and, for audio-lang-detection, an outright different (abbreviated)
# word — NOT a straightforward underscore->hyphen swap. Passing a metering
# key straight into ModelRepository's Model.task["type"].astext.in_(...)
# filter would silently match zero rows for these four, undercounting
# total_models/active_models for exactly the task types this mapping
# exists to fix. "pipeline" has no Registry/TaskTypeEnum equivalent at all
# (it's a metering-only bucket, not a registrable model task) and is
# deliberately omitted — see _to_registry_task_types.
_METERING_TASK_TO_REGISTRY_TASK_TYPE: dict[str, str] = {
    "language_detection": "language-detection",
    "speaker_diarization": "speaker-diarization",
    "audio_language_detection": "audio-lang-detection",
    "language_diarization": "language-diarization",
}


def _to_registry_task_types(task_types: list[str]) -> list[str]:
    """Map metering task-type keys to the Registry's own task-type strings
    (see `_METERING_TASK_TO_REGISTRY_TASK_TYPE`) for use in ModelRepository
    calls. Keys with no Registry mapping needed (llm, nmt, asr, ... — already
    identical to their TaskTypeEnum value) pass through unchanged; "pipeline"
    (no Registry equivalent) is dropped rather than passed through as a
    literal string that can never match any mm_models row.
    """
    return [
        _METERING_TASK_TO_REGISTRY_TASK_TYPE.get(t, t)
        for t in task_types
        if t != "pipeline"
    ]


# The inference-type catalogue's `unit` column is the ONE canonical definition
# of which unit each task type BILLS in — the catalogue is the source of truth
# for that decision — but its identifiers
# (audio_minutes, characters, images, requests) are billing/quota vocabulary,
# not display strings: the frontend (ModelConsumptionTab.tsx) renders this
# value verbatim after the number, so passing "audio_minutes" through as-is
# would render "12.35 audio_minutes" instead of "12.35 min". Translate to
# SERVICE_BREAKDOWN_CONFIG's existing short display suffixes before this
# reaches the wire — the catalogue still decides WHICH unit a task uses, this
# table only decides how that unit is spelled for display.
_PPU_UNIT_TO_DISPLAY_SUFFIX: dict[str, str] = {
    "tokens": "tokens",
    "characters": "chars",
    "audio_minutes": "min",
    "images": "images",
    "requests": "requests",
}


def _native_unit_suffix_for_metering_task(
    task: Optional[str], unit_map: dict[str, str]
) -> str:
    """Never returns None for a resolvable task — the FE's Zod schema
    declares this field a plain `z.string()`, and `parseResponseData` fails
    the ENTIRE Model Consumption response (not just one cell) on a type
    mismatch, so a null here for a single row's unresolved task type is far
    worse than a fallback string.

    That fallback is `""`, not a word like "requests": `formatNativeConsumption`
    prints the number alone when the suffix is empty, whereas any actual word
    renders as a misleading unit label (e.g. "0 requests") sitting right next
    to a Requests column already showing the real count for that row.

    ``unit_map`` is the catalogue's {name: unit}, threaded in by the async
    caller. This function is sync and reached from static/class methods, so it
    cannot fetch it itself; an empty map simply falls through to
    SERVICE_BREAKDOWN_CONFIG, which is the pre-PPU behaviour and is safe.
    """
    if task:
        registry_task_type = _METERING_TASK_TO_REGISTRY_TASK_TYPE.get(task, task)
        ppu_unit = unit_map.get(registry_task_type)
        if ppu_unit:
            return _PPU_UNIT_TO_DISPLAY_SUFFIX.get(ppu_unit, ppu_unit)
        cfg = SERVICE_BREAKDOWN_CONFIG.get(task)
        if cfg:
            return cfg["native_unit_suffix"]
    return ""


class _Unset:
    """Sentinel type distinguishing "caller didn't pass valid_names" from an
    explicit `None` (a legitimate "auth DB was unavailable" value returned
    by _fetch_valid_tenant_ids) — see MeteringService.active_tenants. Its
    own type — rather than a bare ``object()`` typed as ``Any`` — lets the
    parameter annotation say what's actually accepted: a set, None, or this
    sentinel."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<UNSET>"


_UNSET = _Unset()


class MeteringService:
    def __init__(
        self,
        client: PrometheusClient,
        auth_db: Optional[AsyncSession] = None,
        service_repo: Optional[ServiceRepository] = None,
        model_repo: Optional[ModelRepository] = None,
    ) -> None:
        self._client = client
        self._auth_db = auth_db
        self._service_repo = service_repo
        self._model_repo = model_repo

    async def _safe_rollback_auth_db(self) -> None:
        """Best-effort rollback after a swallowed self._auth_db failure — every
        auth_db-touching method here degrades to None/{} rather than raising,
        and overview_tenant_data() reuses the same session across several of
        them sequentially, so leaving it in an aborted-transaction state would
        turn one flaky query into every query after it failing too. Rollback
        failing itself must never escalate an already-degraded path into a
        harder failure than the one it's recovering from."""
        try:
            await self._auth_db.rollback()
        except Exception:
            logger.warning("Auth DB rollback after failed query also failed", exc_info=True)

    # ── public methods ──────────────────────────────────────────────────────

    async def request_total(
        self,
        inference_only: bool,
        tenant: Optional[str],
        service_id: Optional[str],
        time_range: Optional[str],
        task_types: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
        auth_type: Optional[str] = None,
    ) -> dict:
        """KNOWN CUTOVER GAP when ``tenant_id`` is given (this is the
        single-tenant-scoped Overview view): see build_base_selectors'
        docstring — accepted, not fixed here, tracked in the ticket."""
        task_sel = build_task_type_selector(task_types)
        extra = [task_sel] if task_sel else None
        success_extra = [task_sel, 'status_code=~"2.."'] if task_sel else ['status_code=~"2.."']
        label_str = build_base_selectors(
            inference_only, tenant, service_id, extra=extra, tenant_id=tenant_id, auth_type=auth_type
        )
        success_label_str = build_base_selectors(
            inference_only, tenant, service_id, extra=success_extra, tenant_id=tenant_id, auth_type=auth_type
        )
        base = f"{_METRIC}{label_str}"
        success_base = f"{_METRIC}{success_label_str}"
        window = TIME_RANGES.get(time_range or "all")
        rate_window = window or "5m"

        current_queries = [
            self._client.scalar(sum_over_window(base, time_range)),          # 0: total
            self._client.scalar(sum_over_window(success_base, time_range)),  # 1: success
            self._client.scalar(f"sum(rate({base}[{rate_window}]))"),        # 2: avg rps
        ]
        prev_queries = (
            [
                self._client.scalar(f"sum(increase({base}[{window}] offset {window}))"),          # 3: prev total
                self._client.scalar(f"sum(increase({success_base}[{window}] offset {window}))"),  # 4: prev success
                self._client.scalar(f"sum(rate({base}[{window}] offset {window}))"),              # 5: prev avg rps
            ]
            if window
            else []
        )

        raw = await asyncio.gather(*current_queries, *prev_queries, return_exceptions=True)

        def _float(r, default: float = 0.0) -> float:
            return float(r) if not isinstance(r, Exception) else default

        total_v = round(_float(raw[0]))
        success_v = round(_float(raw[1]))
        # 4dp, not 2 — a real but sparse rate (e.g. 112 requests over a 24h
        # window ≈ 0.0013 req/s) rounds to a misleading 0.0 at 2dp even
        # though traffic did occur. The frontend's formatMeteringRps()
        # already renders up to 4dp for values < 1; this just gives it
        # something non-zero to show.
        avg_rps_v = round(_float(raw[2]), 4)
        success_rate = round(success_v / total_v * 100, 2) if total_v else 0.0
        raw_failed = total_v - success_v
        if raw_failed < 0:
            # Independent total/success queries can skew across a scrape boundary,
            # making success briefly exceed total. Clamp to 0 but flag it.
            logger.warning(
                "Failed-count clamp: success(%s) > total(%s) — Prometheus query skew; reporting 0 failed.",
                success_v, total_v,
            )
        failed_v = max(0, raw_failed)

        total_vs_prev: Optional[float] = None
        success_rate_vs_prev: Optional[float] = None
        avg_rps_vs_prev: Optional[float] = None
        failed_vs_prev: Optional[float] = None
        successful_vs_prev: Optional[float] = None
        prev_total_v: Optional[int] = None
        prev_failed_v: Optional[int] = None
        prev_success_v: Optional[int] = None
        prev_success_rate_v: Optional[float] = None
        prev_avg_rps_v: Optional[float] = None

        if window:
            prev_total = max(0, round(_float(raw[3])))
            prev_success = max(0, round(_float(raw[4])))
            prev_avg_rps = _float(raw[5])
            prev_failed = max(0, prev_total - prev_success)
            prev_total_v = prev_total
            prev_failed_v = prev_failed
            prev_success_v = prev_success
            prev_avg_rps_v = round(prev_avg_rps, 4)
            # Previous success rate is undefined without prior traffic → report 0.
            prev_success_rate_v = (
                round(prev_success / prev_total * 100, 2) if prev_total > 0 else 0.0
            )

            if prev_total > 0:
                total_vs_prev = round((total_v - prev_total) / prev_total * 100, 1)
                # pp change so that "97.35 → 97.45" reports as +0.1
                success_rate_vs_prev = round(success_rate - prev_success_rate_v, 2)

            if prev_failed > 0:
                failed_vs_prev = round((failed_v - prev_failed) / prev_failed * 100, 1)

            if prev_success > 0:
                successful_vs_prev = round((success_v - prev_success) / prev_success * 100, 1)

            if prev_avg_rps > 0:
                avg_rps_vs_prev = round((avg_rps_v - prev_avg_rps) / prev_avg_rps * 100, 1)

        return {
            "total_requests": {
                "count": total_v,
                "formatted": self._format_count(total_v),
                "vs_previous_pct": total_vs_prev,
                "previous_count": prev_total_v,
                "previous_formatted": (
                    self._format_count(prev_total_v) if prev_total_v is not None else None
                ),
            },
            "successful_requests": {
                "count": success_v,
                "formatted": self._format_count(success_v),
                "vs_previous_pct": successful_vs_prev,
                "previous_count": prev_success_v,
                "previous_formatted": (
                    self._format_count(prev_success_v) if prev_success_v is not None else None
                ),
            },
            "failed_requests": {
                "count": failed_v,
                "formatted": self._format_count(failed_v),
                "vs_previous_pct": failed_vs_prev,
                "previous_count": prev_failed_v,
                "previous_formatted": (
                    self._format_count(prev_failed_v) if prev_failed_v is not None else None
                ),
            },
            "success_rate": {
                "rate_pct": success_rate,
                "vs_previous_pct": success_rate_vs_prev,
                "previous_rate_pct": prev_success_rate_v,
            },
            "avg_rps": {
                "value": avg_rps_v,
                "vs_previous_pct": avg_rps_vs_prev,
                "previous_value": prev_avg_rps_v,
            },
            "filters": {
                "inference_only": inference_only,
                "tenant": tenant,
                "service_id": service_id,
                "time_range": time_range or "all",
            },
        }

    async def active_tenants(
        self, time_range: Optional[str], valid_names: Union[set, None, _Unset] = _UNSET
    ) -> dict:
        """
        Groups by ``tenant_id`` (immutable) primarily, not ``tenant`` (the
        organisation name) — a tenant rename changes the name label on new
        series but never the id. The PromQL groups by BOTH labels (see
        _by_tenant_promql) so a pre-cutover row (empty tenant_id) still
        carries a usable name instead of being dropped; _merge_tenant_rows
        then re-merges rows sharing a real tenant_id back into one entry, so
        a same-window rename still shows as one continuous tenant rather
        than splitting. See ObservabilityMiddleware for how both labels are
        set.

        `valid_names`: pass a pre-fetched set of currently-ACTIVE tenant ids
        (or None, meaning "auth DB was unavailable, don't filter") when
        calling this for multiple windows in the same request — see
        `overview_tenant_data`. self._auth_db is a single AsyncSession and is
        NOT safe for concurrent use (same constraint as tenant_count()), so
        gathering several `active_tenants()` calls together while each
        independently fetches its own valid ids via `_fetch_valid_tenant_ids()`
        intermittently raises `sqlalchemy.exc.InvalidRequestError: This
        session is provisioning a new connection`.

        Left unset (the default), this fetches the valid-id set internally
        AND resolves each row's tenant_id to its current organisation name
        via `_resolve_tenant_names` — safe for a single, standalone call to
        this method. When `valid_names` is explicitly passed (set or None),
        name resolution is skipped too (the raw `tenant` Prometheus label is
        shown instead): `overview_tenant_data` fires several of these calls
        concurrently sharing one pre-fetched set, and a per-call name
        resolution query would touch the single AsyncSession concurrently —
        the exact bug this parameter exists to avoid. That caller only reads
        this method's `count` anyway, so the resolved display list is a
        bonus reserved for standalone (unset) calls.
        """
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, auth_type=API_KEY_AUTH_TYPE)}"
        promql = self._by_tenant_promql(metric, time_range, filter_zero=True)
        resolve_names = valid_names is _UNSET
        if valid_names is _UNSET:
            prom_results, valid_names = await asyncio.gather(
                self._client.query(promql),
                self._fetch_valid_tenant_ids(),
            )
        else:
            prom_results = await self._client.query(promql)
        # Filter Prometheus results to only tenants that are currently ACTIVE
        # in the DB. Without this, deleted tenants (or tenants that are no
        # longer ACTIVE) whose Prometheus series are still within the
        # retention window inflate the count. Only a non-empty tenant_id can
        # be checked this way — a pre-cutover row (empty tenant_id) can't be
        # validated against the DB, so it's kept rather than dropped: losing
        # 30d of every tenant's history right after deploy is worse than
        # occasionally keeping a stale/deleted tenant's last pre-cutover
        # traffic for that same window (it ages out of the window on its
        # own, same tradeoff documented on `model_breakdown`).
        rows = [
            r for r in prom_results
            if valid_names is None
            or not r["metric"].get("tenant_id")
            or r["metric"].get("tenant_id") in valid_names
        ]
        merged = self._merge_tenant_rows(rows)
        names = (
            await self._resolve_tenant_names({m["tenant_id"] for m in merged if m["tenant_id"]})
            if resolve_names else {}
        )
        tenants = [
            {
                "tenant": names.get(m["tenant_id"], "") or m["tenant"] or "unknown",
                "request_count": int(m["value"]),
            }
            for m in merged
        ]
        return {
            "active_tenants": tenants,
            "count": len(tenants),
            "filters": {"time_range": time_range or "all"},
            "promql": promql,
        }

    async def active_tenants_count_previous(self, time_range: Optional[str]) -> Optional[int]:
        """Count of tenants active in the PREVIOUS window (offset by one window).

        Used as the denominator for avg_requests_per_tenant's vs-previous trend.
        Returns None when there's no bounded window (e.g. time_range='all').

        Counts DISTINCT REAL TENANTS the same way active_tenants does — group
        by (tenant_id, tenant), then _merge_tenant_rows — not a raw
        count(sum by(tenant_id)), which would merge every different
        pre-cutover tenant (they all share an empty tenant_id) into a single
        group and undercount, inflating the vs-previous trend (and, via
        avg_per_active_tenant_previous, the reported average requests per
        tenant too).
        """
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return None
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, auth_type=API_KEY_AUTH_TYPE)}"
        promql = f"sum by(tenant_id, tenant)(increase({metric}[{window}] offset {window}) > 0)"
        try:
            rows = await self._client.query(promql)
            return len(self._merge_tenant_rows(rows))
        except Exception:
            return None

    async def avg_per_active_tenant_previous(
        self, time_range: Optional[str], tenant: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[int]:
        """Avg requests per active tenant in the PREVIOUS window (offset by one
        window) — same offset pattern as request_total's prev counts. Drives the
        Avg-Requests-Per-Tenant trend. None when unbounded or no prior activity.

        KNOWN CUTOVER GAP when ``tenant_id`` is given: see
        build_base_selectors' docstring — accepted, not fixed here, tracked
        in the ticket."""
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return None
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, tenant=tenant, tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE)}"
        total_q = f"sum(increase({metric}[{window}] offset {window}))"
        # See active_tenants_count_previous — same (tenant_id, tenant) +
        # _merge_tenant_rows treatment, so this doesn't undercount active
        # tenants (and inflate the resulting average) whenever several
        # different pre-cutover tenants share an empty tenant_id.
        active_q = f"sum by(tenant_id, tenant)(increase({metric}[{window}] offset {window}) > 0)"
        try:
            total, active_rows = await asyncio.gather(
                self._client.scalar(total_q), self._client.query(active_q)
            )
            active_v = len(self._merge_tenant_rows(active_rows))
            total_v = float(total)
            return round(total_v / active_v) if active_v > 0 else None
        except Exception:
            logger.warning("avg_per_active_tenant_previous: Prometheus query failed", exc_info=True)
            return None

    async def tenant_count(self) -> dict:
        if self._auth_db is None:
            return {
                "total_tenants": None,
                "new_tenants": None,
                "auth_db_available": False,
            }
        try:
            # AsyncSession is not concurrency-safe — run sequentially, not via gather.
            total = await self._auth_db.execute(text("SELECT COUNT(*) FROM tenants"))
            # Truncate to the current UTC calendar day before subtracting 15
            # days, rather than a raw `NOW() - INTERVAL '15 days'` (sub-day
            # precision). A rolling timestamp cutoff splits tenants created
            # on the same calendar day across the boundary depending on the
            # time of day the request happens to run, and drifts hour to
            # hour with no tenant being added/removed — both make this KPI
            # impossible to reconcile against a human reading the "Onboarded"
            # date column on the Institution Management page, which counts
            # in whole calendar days.
            # 14, not 15: today counts as one of the 15 days. `- timedelta(days=15)`
            # would put the cutoff on the 16th-day-back's midnight, so the
            # window [cutoff, now] spans 16 calendar days (e.g. "today" Sep 3
            # minus 15 days lands on Aug 19, and Aug 19..Sep 3 inclusive is 16
            # days) — silently over-counting by a full extra day.
            today_utc_midnight = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            new_tenants_cutoff = today_utc_midnight - timedelta(days=14)
            new_tenants = await self._auth_db.execute(
                text("SELECT COUNT(*) FROM tenants WHERE created_at >= :cutoff"),
                {"cutoff": new_tenants_cutoff},
            )
            return {
                "total_tenants": total.scalar(),
                "new_tenants": new_tenants.scalar(),
                "auth_db_available": True,
            }
        except Exception:
            logger.warning("tenant_count: auth DB query failed", exc_info=True)
            # overview_tenant_data() reuses self._auth_db for
            # _fetch_valid_tenant_ids() right after this call — without a
            # rollback, a failure here would leave that next, otherwise-fine
            # query degraded too (same hazard as UsageService._resolve_tenant_names).
            await self._safe_rollback_auth_db()
            return {
                "total_tenants": None,
                "new_tenants": None,
                "auth_db_available": False,
            }

    async def model_usage_growth_pct(self) -> Optional[float]:
        """Overall LLM request volume, current calendar month-to-date vs the
        previous calendar month — fixed regardless of the dashboard's
        `window` filter (Key Metrics KPI #7). Distinct from both
        request_total()'s vs_previous_pct (a rolling window that follows
        `window`) and the pay-per-use "vs last month" comparison (spend, not
        request volume).

        Uses exact elapsed-second widths (not `@`, unsupported by some
        Prometheus deployments) to bound exact calendar-month boundaries,
        the same offset-based technique request_total() uses for its
        rolling-window comparison. `cur_q` goes through sum_over_window()
        (the reset-aware `unless ... offset` hybrid) rather than a bare
        increase(), same as request_total()'s "current" query — over a
        ~30-day month-to-date window a mid-month pod redeploy is exactly
        the kind of young series increase() would extrapolate up by
        window/observed_duration, inflating cur_total.

        `prev_q` deliberately compares the SAME width (`elapsed_s`) on both
        sides, not the previous month's full length — comparing 5 days of
        August against all 31 days of July would report ~-84% on Aug 5th
        even with flat traffic. `[elapsed_s]s offset prev_month_len_s` looks
        back `elapsed_s` from `now - prev_month_len_s`, which lands exactly
        on `[prev_month_start, prev_month_start + elapsed_s]` — the same
        number of days into July as `cur_q`'s days into August. Near
        month-end this needs history back to `elapsed_s + prev_month_len_s`
        (~60 days).

        This repo ships no production Prometheus config — every deployer
        runs their own, with their own retention — so that requirement
        can't be enforced from a config file here. Instead, before firing
        `prev_q` this method compares how far back it needs against
        `settings.prometheus_retention_days` (env `PROMETHEUS_RETENTION_DAYS`,
        default 15 — Prometheus's own out-of-box default, deliberately
        conservative) and returns None outright if the deployment hasn't
        declared enough retention to cover it. Without this guard,
        Prometheus would silently answer from whatever partial data
        survived retention and `prev_total` would under-count rather than
        the method returning the `None` it promises — an operator must
        opt in (set `PROMETHEUS_RETENTION_DAYS` to match their actual
        `--storage.tsdb.retention.time`, >= ~90d recommended) before this
        KPI computes a real percentage.

        Returns None if it's too early in the month for a meaningful window,
        the declared retention can't cover the previous-month lookback, the
        previous month had no traffic (percentage undefined), or the
        Prometheus query fails.
        """
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elapsed_s = int((now - month_start).total_seconds())
        if elapsed_s < 60:
            return None

        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
        prev_month_len_s = int((month_start - prev_month_start).total_seconds())

        lookback_days_needed = (elapsed_s + prev_month_len_s) / 86400
        if lookback_days_needed > settings.prometheus_retention_days:
            logger.info(
                "model_usage_growth_pct: skipping — needs %.1fd of history, "
                "PROMETHEUS_RETENTION_DAYS=%d",
                lookback_days_needed, settings.prometheus_retention_days,
            )
            return None

        sel = build_base_selectors(
            inference_only=True, endpoint_regex=LLM_CHAT_ENDPOINT_REGEX, auth_type=API_KEY_AUTH_TYPE,
        )
        base = f"{_METRIC}{sel}"
        cur_q = sum_over_window(base, f"{elapsed_s}s")
        prev_q = f"sum(increase({base}[{elapsed_s}s] offset {prev_month_len_s}s))"

        try:
            cur_v, prev_v = await asyncio.gather(self._client.scalar(cur_q), self._client.scalar(prev_q))
        except Exception:
            logger.warning("model_usage_growth_pct: Prometheus query failed", exc_info=True)
            return None

        prev_total = max(0, round(float(prev_v)))
        cur_total = max(0, round(float(cur_v)))
        if prev_total <= 0:
            return None
        return round((cur_total - prev_total) / prev_total * 100, 1)

    async def overview_tenant_data(
        self, time_ranges: list[str]
    ) -> tuple[dict, dict[str, dict]]:
        """Fetch `tenant_count()` plus `active_tenants()` for several windows
        (the Overview tab needs 24h/7d/30d) in one call, respecting the
        constraint that `self._auth_db` — a single AsyncSession — is NOT
        safe for concurrent use (see `tenant_count()`'s comment).

        `tenant_count()`'s 2 queries and the ONE valid-tenant-names fetch
        shared across every window all run sequentially first (each already
        catches its own DB errors internally and never raises, so this can't
        regress a caller's degraded-response handling); only then are the
        per-window Prometheus queries fired concurrently via
        `active_tenants(tr, valid_names=...)`. Calling `active_tenants()`
        directly, once per window, inside the SAME outer `asyncio.gather` as
        `tenant_count()` (as the /overview route used to) intermittently
        raises `sqlalchemy.exc.InvalidRequestError: This session is
        provisioning a new connection; concurrent operations are not
        permitted` — multiple tasks each trying to run their own
        `self._auth_db.execute()` at the same time.

        The per-window gather uses `return_exceptions=True`: unlike
        tenant_count()/the valid-names fetch, active_tenants() does NOT
        catch a Prometheus query failure internally (it can genuinely
        raise), so without this a single bad window would propagate out of
        this method entirely — the caller (routes/metering.py) never gets a
        chance to run it through `_partition_results` and degrade
        gracefully; /overview would 500 instead.

        Returns (tenant_count_result, {time_range: active_tenants_result_or_exception}).
        """
        tc = await self.tenant_count()
        valid_names = await self._fetch_valid_tenant_ids()
        active_results = await asyncio.gather(
            *(self.active_tenants(tr, valid_names=valid_names) for tr in time_ranges),
            return_exceptions=True,
        )
        return tc, dict(zip(time_ranges, active_results))

    async def usage_concentration(
        self, limit: int, time_range: Optional[str], task_types: Optional[list[str]] = None,
    ) -> dict:
        task_sel = build_task_type_selector(task_types)
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, extra=[task_sel] if task_sel else None, auth_type=API_KEY_AUTH_TYPE)}"
        promql = self._by_tenant_promql(metric, time_range, filter_zero=False)
        results = await self._client.query(promql)
        rows = [r for r in results if float(r["value"][1]) > 0]
        # A tenant renamed WITHIN this window produces two rows sharing one
        # tenant_id but different tenant labels (see _by_tenant_promql's
        # `by(tenant_id, tenant)`) — merge them back into one row so the
        # rename doesn't split the tenant's traffic. Pre-cutover rows (empty
        # tenant_id) have nothing else to merge by, so they're kept as their
        # own entry under whatever name they carried, instead of being
        # dropped or collapsing into one "unknown" bucket.
        merged = self._merge_tenant_rows(rows)
        names = await self._resolve_tenant_names({m["tenant_id"] for m in merged if m["tenant_id"]})

        all_tenants = sorted(
            [
                {
                    "tenant": names.get(m["tenant_id"], "") or m["tenant"] or "unknown",
                    "requests": max(1, round(m["value"])),
                }
                for m in merged
            ],
            key=lambda t: t["requests"],
            reverse=True,
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
            "promql": promql,
        }

    async def service_breakdown(
        self, tenant: Optional[str], time_range: Optional[str],
        service_filter: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> dict:
        """Per-service stats: requests, native units, success %, failed, vs prev period.

        Fires all Prometheus queries in a single asyncio.gather:
          - 4–5 endpoint-grouped queries for request counts / prev period
          - 1 scalar query per service that has a dedicated native-unit metric

        KNOWN CUTOVER GAP when ``tenant_id`` is given: see
        build_base_selectors' docstring — accepted, not fixed here, tracked
        in the ticket.
        """
        # Fetched once per request, then threaded through the sync helpers that
        # need it — they are static/class methods and cannot await.
        unit_map = await inference_type_cache.get_unit_map_standalone()
        # Use the broader regex so /api/v1/chat (LLM) is included alongside
        # the standard /api/v1/{task}/inference endpoints.
        _ep = f'{PROMETHEUS_API_PATH_LABEL}=~"{SERVICE_BREAKDOWN_ENDPOINT_REGEX}"'
        # tenant_id (immutable) is preferred over tenant (the organisation
        # name) so this survives a tenant rename — see build_base_selectors.
        _tenant_part = (
            f',tenant_id="{escape_label_value(tenant_id)}"' if tenant_id
            else (f',tenant="{escape_label_value(tenant)}"' if tenant else "")
        )
        _base = (
            _ep + ',tenant!="unknown"' + _tenant_part
            + ',' + api_key_auth_type_selector()
        )
        base_sel    = "{" + _base + "}"
        success_sel = "{" + _base + ',status_code=~"2.."' + "}"

        window = TIME_RANGES.get(time_range or "all")

        fixed_queries = [
            self._client.query(self._service_breakdown_by_ep_promql(base_sel, window)),     # 0 total
            self._client.query(self._service_breakdown_by_ep_promql(success_sel, window)),  # 1 success
        ]
        native_tasks, native_coros = self._native_unit_queries(
            tenant, time_range, service_filter, tenant_id=tenant_id
        )

        raw = await asyncio.gather(*fixed_queries, *native_coros, return_exceptions=True)

        totals = self._endpoint_dict(self._safe(raw[0], []))
        successes = self._endpoint_dict(self._safe(raw[1], []))
        natives = self._unpack_native_units(native_tasks, raw, native_offset=len(fixed_queries))

        return {
            "services": self._service_breakdown_rows(
                totals, successes, natives, unit_map, service_filter
            ),
            "filters": {"tenant": tenant, "time_range": time_range or "all"},
        }

    async def model_breakdown(
        self, tenant: Optional[str], time_range: Optional[str],
        tenant_id: Optional[str] = None,
        task_types: Optional[list[str]] = None,
    ) -> dict:
        """Usage grouped by BOTH `service_id` (the tenant-facing service
        the client called — the OpenAI `model` field as sent) AND `model_id`
        (the Registry's stable identity for the model actually behind that
        service, stamped server-side by inference-service at MMS-resolution
        time — see ai4i-core 1.0.18's `MetricsCollector` — NOT derived from
        anything the client sends). One PromQL pass, `by (service_id,
        model_id)`, so both dimensions come from the same series: `services`
        below is the per-service breakdown (one row per service_id, for the
        "service" column), and the model-level rollup consumed by
        `model_consumption_ranking`/`model_consumption_kpis` is computed
        independently from the same raw rows, collapsed by `model_id` alone
        — see the second ROLLOUT NOTE below for why that's deliberately NOT
        just "re-aggregate the (ghost-filtered) `services` list".

        The `model` label (the upstream inference engine's own echoed model
        name — absent on failures, can differ between the buffered/streaming
        paths) is intentionally never grouped or filtered on; `model_name`
        below is always the Registry's name for `model_id`, not this label.

        `task_types`, when given, scopes the query to those task types only
        (LLM + NLP alike — same `build_task_type_selector` used by
        service_breakdown/usage_concentration/etc); `None` covers every task
        type. Each row's own `task_type` is resolved from the SAME
        `PROMETHEUS_API_PATH_LABEL` (endpoint) label the request itself
        carries on `telemetry_obsv_requests_total`, via `_resolve_task_key`
        — the same endpoint->task resolution service_breakdown/
        usage_by_tenant_service already use elsewhere in this module — NOT a
        separate Model Registry lookup. That task_type then picks the row's
        native-unit metric and suffix from SERVICE_BREAKDOWN_CONFIG, same
        per-task-type metrics service_breakdown() already uses — an NLP row
        reports its own unit (chars/min/images/...), not LLM tokens.

        Fires 2 fixed queries (total requests, successful requests, each
        grouped by `(service_id, model_id, endpoint)` — the endpoint dimension
        is what task_type is read from) plus one additional query per
        native-unit metric in scope (task_types, or every
        SERVICE_BREAKDOWN_CONFIG task when unfiltered), each grouped by
        `service_id` alone since none of those per-task Histograms carry a
        `model_id` label (see metrics.py) — all in one asyncio.gather.

        ROLLOUT NOTE (service-level ghosts): per-service rows are
        cross-checked against the Service Registry (mm_services) via
        ServiceRepository.get_names_and_models_by_service_ids, and a
        `service_id` whose model row is entirely absent from mm_models is
        dropped from `services` — a DEPRECATED model is NOT a ghost (it's
        still live and can still be serving traffic; see that method's
        docstring), only a hard-deleted one is. Two different populations
        land here: `service_id` is the client-supplied `model` string, set
        before MMS resolution, so a request for a service that was deleted,
        OR one that never existed (a typo, a stale integration still
        pointing at an old id — the `llm`/`llm/default` cases) both emit
        Prometheus series but neither has a current registry row. We can't
        tell those apart here, so both are dropped from the per-service
        breakdown. The check is skipped (all ids kept, name falls back to
        the raw id) only when the registry lookup itself is unavailable or
        errors — we can't tell "deleted" from "DB unreachable" in that
        case. Suppressed ids are logged so a delete-induced drop is
        traceable.

        ROLLOUT NOTE (model-level totals are NOT a re-aggregation of
        `services`): a model's own requests/success/tokens are collapsed
        directly from the raw `(service_id, model_id)` rows and validated
        against the Registry by `model_id` alone (ModelRepository.
        get_model_names — same "absent row = ghost, DEPRECATED is not"
        rule) — deliberately NOT derived by summing the
        (service-existence-filtered) `services` list above. If a
        contributing service is later deleted while its model row still
        exists, the model's total must not silently shrink just because one
        of several services feeding it disappeared — that's real traffic
        the model actually served. The consequence: `services` (the flat
        per-service breakdown) can sum to LESS than its parent model's own
        total for as long as that deleted service's old series remain in
        the query window — the same "won't add up exactly, self-heals as
        old series age out" tradeoff `active_tenants` documents for the
        tenant-id -> org-name cutover.

        Each per-service row's own `model_id` is read straight from the
        Prometheus label when present (the new source of truth), falling
        back to the DB-joined value from `get_names_and_models_by_service_ids`
        only when no row for that service_id carried a non-empty `model_id`
        yet — i.e. a legacy pre-upgrade series (recorded before ai4i-core
        1.0.18 started stamping this label) or a resolution failure. This
        self-heals as pre-upgrade series age out of the window; there's no
        after-the-fact fix, same reasoning as the tenant-id cutover.
        """
        # Fetched once per request; the sync helpers below cannot await.
        unit_map = await inference_type_cache.get_unit_map_standalone()
        # No task_types filter -> every task type's endpoints (LLM chat AND
        # every /api/v1/{task}/inference path), via the default
        # INFERENCE_ENDPOINT_REGEX build_base_selectors already applies when
        # endpoint_regex is omitted. A given task_types list narrows to just
        # those tasks' endpoints, same selector build used elsewhere
        # (service_breakdown, usage_concentration, /overview).
        task_sel = build_task_type_selector(task_types)
        base_sel = build_base_selectors(
            inference_only=True, tenant=tenant, extra=[task_sel] if task_sel else None,
            tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE,
        )
        success_sel = build_base_selectors(
            inference_only=True, tenant=tenant,
            extra=[task_sel, 'status_code=~"2.."'] if task_sel else ['status_code=~"2.."'],
            tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE,
        )
        group_by = f"service_id, model_id, {PROMETHEUS_API_PATH_LABEL}"
        total_q = sum_over_window_by(f"{_METRIC}{base_sel}", group_by, time_range)
        success_q = sum_over_window_by(f"{_METRIC}{success_sel}", group_by, time_range)
        # One additional query per native-unit metric IN SCOPE (task_types,
        # or every SERVICE_BREAKDOWN_CONFIG task when unfiltered) — mirrors
        # service_breakdown's _native_unit_queries, but grouped by service_id
        # (not a single scalar) since each row here needs its OWN value, not
        # a tenant-wide total. Restricting to task_types avoids the same
        # ghost-row problem the old LLM-only gating existed to prevent: an
        # explicit NLP-only filter (e.g. ["nmt"]) must not pull in, say, an
        # LLM model_id that has no rows in total_q/success_q under that filter.
        native_tasks, native_coros = self._model_native_unit_queries(
            tenant, tenant_id, time_range, task_types
        )

        raw = await asyncio.gather(
            self._client.query(total_q),
            self._client.query(success_q),
            *native_coros,
            return_exceptions=True,
        )

        def _safe_list(r):
            return r if not isinstance(r, Exception) else []

        total_rows = _safe_list(raw[0])
        success_rows = _safe_list(raw[1])
        # task -> {service_id: raw float value} — unrounded; each row rounds
        # its own value below per SERVICE_BREAKDOWN_CONFIG's `round_2dp`.
        native_by_task: dict[str, dict[str, float]] = {
            task: self._native_units_by_service(_safe_list(raw[2 + i]))
            for i, task in enumerate(native_tasks)
        }

        # ── Per-service view (collapses across model_id — see class docstring
        # on why a service_id can transiently carry more than one model_id
        # label value; the per-service TOTAL must not fragment because of it).
        totals = self._label_dict(total_rows, "service_id")
        successes = self._label_dict(success_rows, "service_id")

        # task_type per service_id, read straight off the SAME endpoint label
        # every request already carries (PROMETHEUS_API_PATH_LABEL) — the
        # same source of truth _resolve_task_key backs elsewhere in this
        # module (service_breakdown, usage_by_tenant_service's heatmap). No
        # Model Registry lookup involved: a service serves exactly one task
        # (its endpoint never varies), so the first row seen for a
        # service_id settles it.
        service_task: dict[str, str] = {}
        for r in (*total_rows, *success_rows):
            sid = r["metric"].get("service_id", "")
            if not sid or sid in service_task:
                continue
            task = self._resolve_task_key(r["metric"].get(PROMETHEUS_API_PATH_LABEL, ""))
            if task:
                service_task[sid] = task

        # "" means the client sent no `model` field at all — not a real service.
        service_ids = {
            s for s in (
                set(totals) | set(successes)
                | {sid for by_service in native_by_task.values() for sid in by_service}
            )
            if s != ""
        }

        # Representative model_id per service_id, straight from Prometheus —
        # first non-empty value seen wins (a service's model_id is an
        # immutable FK, so in steady state there's only ever one; see the
        # ROLLOUT NOTE above for the transitional exception).
        prom_model_id: dict = {}
        for r in (*total_rows, *success_rows):
            sid = r["metric"].get("service_id", "")
            mid = r["metric"].get("model_id", "") or ""
            if sid and mid and sid not in prom_model_id:
                prom_model_id[sid] = mid

        svc_info: dict = {}
        registry_checked = False
        if self._service_repo is not None and service_ids:
            try:
                svc_info = await self._service_repo.get_names_and_models_by_service_ids(
                    list(service_ids)
                )
                registry_checked = True
            except Exception:
                logger.warning("model_breakdown: service name/model lookup failed", exc_info=True)

        # service_id with no current row at all in mm_models (a DEPRECATED
        # model still has a row, so it's not a ghost — see the service-level
        # ROLLOUT NOTE above). Only computed when the registry lookup
        # actually ran — if it's unavailable/failed we can't tell "deleted"
        # from "DB down", so nothing is dropped.
        ghosts = (service_ids - svc_info.keys()) if registry_checked else set()
        if ghosts:
            logger.info(
                "model_breakdown: dropped %d unregistered service_id(s): %s",
                len(ghosts), sorted(ghosts),
            )

        # ── Model registry lookup (names only — task_type comes from
        # service_task above, not the Registry) — computed here, before the
        # per-model rollup below, so `model_ids` is resolved the same way the
        # model-level rollup groups by EFFECTIVE model_id (Prometheus label
        # first, falling back to the DB-joined value from svc_info) — see
        # the ROLLOUT NOTE on model-level totals above for why this is
        # independent of the service-existence filtering `services` goes
        # through.
        def _effective_model_id(row: dict) -> str:
            sid = row["metric"].get("service_id", "")
            _, db_model_id, _ = svc_info.get(sid, (None, None, None))
            return prom_model_id.get(sid) or db_model_id or ""

        model_totals_raw = self._label_dict(total_rows, _effective_model_id)
        model_successes_raw = self._label_dict(success_rows, _effective_model_id)
        model_ids = {
            m for m in (set(model_totals_raw) | set(model_successes_raw))
            if m != ""
        }

        # Same population the Prometheus query itself was scoped to: the
        # requested task_types, or — when unfiltered — every task type this
        # endpoint knows about (not just "llm"), so a model registered under
        # any task type is validated rather than only LLM ones. Converted to
        # the Registry's own task-type strings — see
        # _to_registry_task_types — since e.g. "audio_language_detection"
        # (this module's key) is stored in mm_models as "audio-lang-detection".
        model_registry_task_types = _to_registry_task_types(task_types or list(SERVICE_BREAKDOWN_CONFIG))
        model_names: dict = {}
        model_registry_checked = False
        if not model_registry_task_types:
            # e.g. task_types=["pipeline"] — see registry_model_count's
            # comment on the same mapping. get_model_names() gates on
            # `if task_types:`, so passing [] through would fetch every
            # model_id unfiltered instead of none; there's no Registry
            # equivalent for this scope at all, so every model_id is
            # correctly treated as unregistered (ghosted) without a query.
            model_registry_checked = True
        elif self._model_repo is not None and model_ids:
            try:
                model_names = await self._model_repo.get_model_names(
                    list(model_ids), task_types=model_registry_task_types
                )
                model_registry_checked = True
            except Exception:
                logger.warning("model_breakdown: model registry lookup failed", exc_info=True)

        services = []
        for service_id in service_ids:
            if service_id in ghosts:
                continue
            total_v = totals.get(service_id, 0)
            success_v = successes.get(service_id, 0)
            name, db_model_id, model_name = svc_info.get(service_id, (service_id, None, None))
            model_id = prom_model_id.get(service_id) or db_model_id
            task = service_task.get(service_id)
            native_units, native_unit_suffix = self._native_units_for(
                task, native_by_task, service_id, unit_map
            )
            services.append({
                "service_id": service_id,
                "name": name,
                "model_id": model_id,
                "model_name": model_name,
                "task_type": task,
                "requests": total_v,
                "native_units": native_units,
                "native_unit_suffix": native_unit_suffix,
                "success_pct": round(success_v / total_v * 100, 2) if total_v else 0.0,
            })

        services.sort(key=lambda s: s["requests"], reverse=True)

        # ── Model-level view (collapses across service_id) — the
        # authoritative source for model_consumption_ranking/kpis; see the
        # model-level ROLLOUT NOTE above for why this is independent of the
        # service-existence filtering `services` above went through.
        #
        # model_id with no current Registry row under `model_registry_task_types`
        # — a DEPRECATED model still has a row (see get_model_names) so it's
        # not a ghost on that basis, only a hard-deleted/stale/never-existent
        # id, OR one registered under a different task type, is. That second
        # case matters here specifically: without this filter, a model_id
        # tagged e.g. "asr" in the Registry but actually serving /chat
        # traffic (a Registry data error, not a deletion) would land in
        # active_models without ever counting toward registry_model_count's
        # total_models — this filter keeps both KPIs scoped to the same
        # population. An empty-model_id row (e.g. a pre-upgrade series with
        # no label at all) was already excluded by the `!= ""` filter above
        # and never reaches here.
        #
        # Skipped (nothing dropped) only when the registry lookup itself is
        # unavailable — same graceful-degradation choice `services` above
        # makes for service_id ghosts. This is the one remaining way
        # `active_models` can exceed `total_models` post-fix: a transient
        # DB error here doesn't also fail registry_model_count's separate
        # query, so the two can momentarily disagree. Accepted, not fixed —
        # matches the existing "can't tell deleted from DB down" policy
        # applied everywhere else in this method.
        model_ghosts = (model_ids - model_names.keys()) if model_registry_checked else set()
        if model_ghosts:
            logger.info(
                "model_breakdown: dropped %d unregistered model_id(s): %s",
                len(model_ghosts), sorted(model_ghosts),
            )

        # Native units + task per model_id: summed/resolved from every
        # service_id that resolves to it (same _effective_model_id grouping
        # the request counts above use) — the per-task Histograms have no
        # model_id label of their own (see metrics.py), so this is the only
        # way to roll a native-unit value up from service_id to model_id. A
        # model is fronted by services that all share its one task, so the
        # first task seen for the model settles it, same as service_task
        # does per service_id above.
        model_native_raw: dict[str, float] = {}
        model_task: dict[str, str] = {}
        for service_id in service_ids:
            mid = _effective_model_id({"metric": {"service_id": service_id}})
            if not mid:
                continue
            task = service_task.get(service_id)
            v = native_by_task.get(task, {}).get(service_id, 0.0) if task else 0.0
            model_native_raw[mid] = model_native_raw.get(mid, 0.0) + v
            if task:
                model_task.setdefault(mid, task)

        model_totals = []
        for model_id in model_ids:
            if model_id in model_ghosts:
                continue
            total_v = model_totals_raw.get(model_id, 0)
            success_v = model_successes_raw.get(model_id, 0)
            task = model_task.get(model_id)
            native_units, native_unit_suffix = self._round_native(
                task, model_native_raw.get(model_id, 0.0), unit_map
            )
            model_totals.append({
                "model_id": model_id,
                "model_name": model_names.get(model_id, model_id),
                "task_type": task,
                "requests": total_v,
                "native_units": native_units,
                "native_unit_suffix": native_unit_suffix,
                "success_pct": round(success_v / total_v * 100, 2) if total_v else 0.0,
            })

        return {
            "services": services,
            "model_totals": model_totals,
            "filters": {"tenant": tenant, "time_range": time_range or "all"},
        }

    async def registry_model_count(self, task_types: Optional[list[str]] = None) -> Optional[int]:
        """Count of registered model VERSIONS (`mm_models` rows) — ACTIVE and
        DEPRECATED both count (a deprecated version is still "in the
        Registry", just not the currently-recommended one to use).

        Scoped to the SAME `task_types` model_breakdown's own query was
        scoped to (or every known task type when unfiltered — see
        model_breakdown's `model_registry_task_types`), and identity is
        model_id (one row per version) to match model_totals' own grain, NOT
        distinct model name — a model with 3 concurrently-registered versions
        counts as 3 here, same as it does in the DEFAULT (no
        `include_deprecated` override) `/api/v1/models?task_types=...`
        call's `meta.total` (see ModelRepository.count_models). NOT
        guaranteed to match every call to that endpoint: ModelService.
        list_models never forwards its own `include_deprecated` param to
        `count_models`, so `?task_types=llm&include_deprecated=false`
        already returns an `items` list narrower than its own `meta.total`
        — a pre-existing, separate bug this method's parity claim inherits
        rather than causes.

        This keeps `total_models` and `model_consumption_kpis`'s
        `active_models` (also model_id-grained and identically task-scoped —
        see get_model_names' `task_types` param and that KPI method's
        docstring) counting the same population MOST of the time — not
        guaranteed: a registry-lookup failure inside model_breakdown leaves
        model_totals' ghosts unfiltered (see model_breakdown's comment on
        `model_ghosts`), which is the one path where `active_models` can
        still exceed this count even after the task-type scoping here.

        Not tenant-scoped: ``mm_models`` has no tenant column — the Registry is
        a shared catalog, not partitioned per institution — so this value is
        the same platform-wide regardless of the caller's tenant_id. Returns
        None (never raises) when the DB is unavailable, same pattern as
        tenant_count(), so a Registry lookup failure degrades this one summary
        field instead of the whole response.
        """
        if self._model_repo is None:
            return None
        registry_task_types = _to_registry_task_types(task_types or list(SERVICE_BREAKDOWN_CONFIG))
        # e.g. task_types=["pipeline"] — the only metering task with no
        # Registry equivalent (_to_registry_task_types drops it, never maps
        # it to something real) — maps to []. count_models()/get_model_names()
        # both gate on `if task_types:`, so passing [] through would apply NO
        # filter at all and count every mm_models row instead of zero. There
        # are no registrable models under this scope, by definition — skip
        # the query and answer 0 directly rather than let an empty list
        # silently disable the filter.
        if not registry_task_types:
            return 0
        try:
            return await self._model_repo.count_models(task_types=registry_task_types)
        except Exception:
            logger.warning("registry_model_count: DB query failed", exc_info=True)
            return None

    @staticmethod
    def model_consumption_ranking(
        model_totals: list[dict], limit: int
    ) -> tuple[Optional[dict], list[dict], int]:
        """Rank `model_breakdown`'s already-grouped `model_totals` for the
        Model Consumption summary's `most_used` KPI and the `top_models`
        ranking (AI4IDS-2790).

        Takes `model_totals` (one row per `model_id`, already collapsed
        across every contributing service_id and Registry-validated by
        `model_breakdown` — see its ROLLOUT NOTEs) rather than the flat
        per-service `services` list: grouping now happens at the Prometheus
        query itself (`by (service_id, model_id)`), not here, so a model's
        total is never short-changed by a per-service existence filter this
        function has no visibility into.

        `grand_total` here IS the full sum across `model_totals` — unlike
        the old service-level grouping, there's no separate "unresolved"
        bucket to exclude: `model_breakdown` never emits a `model_totals`
        entry it hasn't already validated against the Registry. Callers
        must still surface this `grand_total` (not some other "total
        requests" figure) alongside `consumption_pct`, or the percentages
        won't add up against whatever total gets displayed next to them.

        consumption_pct per model = this model's total requests / grand_total
        * 100 — its SHARE of total requests. `most_used` and `top_models[0]`
        always name the same model, since both rank on total requests
        (dividing by the same grand_total preserves order).

        Returns (most_used, ranked, grand_total) — most_used/ranked are
        None/[] when there's no traffic at all; grand_total is always an int
        (0 in that case).
        """
        active = [m for m in model_totals if m["requests"] > 0]
        grand_total = sum(m["requests"] for m in active)
        if not active or not grand_total:
            return None, [], 0

        ranked = sorted(
            (
                {
                    "model_id": m["model_id"],
                    "model_name": m["model_name"],
                    "task_type": m.get("task_type"),
                    "requests": m["requests"],
                    "native_units": m.get("native_units", 0.0),
                    "native_unit_suffix": m.get("native_unit_suffix", ""),
                    "consumption_pct": round(m["requests"] / grand_total * 100, 2),
                }
                for m in active
            ),
            key=lambda m: m["requests"],
            reverse=True,
        )

        most_used = ranked[0]

        top = [
            {**m, "rank": idx + 1, "formatted_requests": MeteringService._format_count(m["requests"])}
            for idx, m in enumerate(ranked[:limit])
        ]
        return most_used, top, grand_total

    @staticmethod
    def model_consumption_kpis(services: list[dict], model_totals: list[dict]) -> dict:
        """Scalar KPIs for the Model Consumption summary (AI4IDS-2790):

        - `active_models`: count of DISTINCT `model_id`s among `model_totals`
          entries with traffic (`requests > 0`) — matches `model_totals`/
          `top_models`' own grain (one row per `model_id` — see
          `model_breakdown`) AND `registry_model_count`'s grain (also
          model_id-based, see its docstring), so `active_models` stays a
          subset of `total_models` in the common case, and agrees with the
          row count in the visible `top_models` breakdown when that list
          isn't truncated by the caller's `limit`. NOT an absolute
          guarantee — see registry_model_count's docstring and
          model_breakdown's `model_ghosts` comment for the one remaining
          path (a registry-lookup failure inside model_breakdown) where
          `active_models` can still exceed `total_models`. Two concurrently-ACTIVE
          versions of the same model name both receiving traffic count as
          TWO active models here, matching the two separate rows they
          produce in `model_totals`/`top_models` — deliberately not
          collapsed to one, unlike the old name-based identity this
          replaced. Always an int; 0 (not None) when there's no traffic at
          all — 0 is itself a real, meaningful answer ("no models were
          active"), unlike `overall_success_rate_pct`, which is genuinely
          undefined with no data to average.
        - `overall_success_rate_pct`: REQUEST-WEIGHTED success rate — sum(
          requests * success_pct) / sum(requests) over `services` (not
          `model_totals`) — matching the FE's existing (previously dormant)
          fallback formula, so this field doesn't silently change what the
          dashboard already shows once populated. Deliberately the WIDER,
          service-level population: includes every service with traffic,
          even one whose model lookup failed, since success/failure is a
          traffic-health signal independent of whether the model behind it
          was identifiable. None when there's no traffic to average over.
        - `worst`: the active service with the highest failure rate — raw
          dict, consumed by the caller to build `highest_failure_rate`
          (which stays service-level, not aggregated to model-level). None
          when there's no traffic.
        """
        active_models = len({
            m["model_id"] for m in model_totals if m["requests"] > 0
        })

        active_services = [s for s in services if s["requests"] > 0]
        total_requests = sum(s["requests"] for s in active_services)
        overall_success_rate_pct = (
            round(sum(s["requests"] * s["success_pct"] for s in active_services) / total_requests, 2)
            if total_requests else None
        )
        worst = max(active_services, key=lambda s: 100 - s["success_pct"]) if active_services else None
        return {
            "active_models": active_models,
            "overall_success_rate_pct": overall_success_rate_pct,
            "worst": worst,
        }

    async def tenant_ranking(
        self, limit: int, time_range: Optional[str], tenant: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> dict:
        """KNOWN CUTOVER GAP when ``tenant_id`` is given (scoping the ranking
        to one tenant): see build_base_selectors' docstring — accepted, not
        fixed here, tracked in the ticket. Unscoped (no tenant_id) calls are
        unaffected — they already recover pre-cutover data via the
        (tenant_id, tenant) group-by + _merge_tenant_rows."""
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, tenant=tenant, tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE)}"
        promql = self._tenant_delta_promql(metric, time_range)
        results = await self._client.query(promql)
        rows = [r for r in results if float(r["value"][1]) > 0]
        # See usage_concentration's comment above — same merge-back-by-id,
        # fall-back-to-name-when-empty reasoning applies here.
        merged = self._merge_tenant_rows(rows)
        names = await self._resolve_tenant_names({m["tenant_id"] for m in merged if m["tenant_id"]})

        all_tenants = sorted(
            [
                {
                    "tenant": names.get(m["tenant_id"], "") or m["tenant"] or "unknown",
                    "requests": max(1, round(m["value"])),
                }
                for m in merged
            ],
            key=lambda t: t["requests"],
            reverse=True,
        )

        grand_total = sum(t["requests"] for t in all_tenants)
        active_count = len(all_tenants)
        avg_per_active = round(grand_total / active_count) if active_count else 0
        top = all_tenants[:limit]

        ranked = [
            {
                "rank": idx + 1,
                "tenant": t["tenant"],
                "requests": t["requests"],
                "formatted_requests": self._format_count(t["requests"]),
                "percentage": round(t["requests"] / grand_total * 100, 2) if grand_total else 0.0,
            }
            for idx, t in enumerate(top)
        ]

        return {
            "tenants": ranked,
            "grand_total": grand_total,
            "formatted_grand_total": self._format_count(grand_total),
            "total_tenant_count": active_count,
            "avg_per_active_tenant": avg_per_active,
            "formatted_avg_per_active_tenant": self._format_count(avg_per_active),
            "filters": {"limit": limit, "time_range": time_range or "all"},
        }

    @staticmethod
    def _resolve_task_key(endpoint: str) -> Optional[str]:
        """Map a Prometheus endpoint-path label to its task-type key.

        Falls back to deriving the key from the URL's 3rd path segment
        (e.g. /api/v1/nmt/inference -> "nmt") when ENDPOINT_TO_TASK doesn't
        have an entry for it.
        """
        task = ENDPOINT_TO_TASK.get(endpoint)
        if task is not None:
            return task
        parts = [p for p in endpoint.split("/") if p]
        raw = parts[2] if len(parts) >= 4 else None
        return raw.replace("-", "_") if raw else None

    @classmethod
    def _accumulate_tenant_task_counts(
        cls, results: list, active_services: list[str]
    ) -> dict[str, dict]:
        """merge_key -> {"tenant_id", "tenant", "tasks": {task: count}}, from a
        sum-by(tenant_id, tenant, endpoint) query result.

        merge_key is tenant_id when present, so a same-window rename (which
        produces rows sharing one tenant_id but different tenant labels)
        buckets into ONE entry instead of splitting across two. For a row
        with no tenant_id, a first pass over `results` learns tenant_id from
        any OTHER row sharing its tenant name (see _merge_tenant_rows for the
        full reasoning) — this is what keeps a tenant whose traffic spans
        the pre/post-cutover boundary as one bucket instead of two. Only
        when no id can be found for the name at all does it fall back to a
        name-only bucket, so genuinely unresolvable pre-cutover rows are
        still kept and shown under their own name instead of being dropped
        or collapsing into one "unknown" pseudo-tenant that could out-rank a
        real one."""
        id_by_name: dict[str, str] = {}
        for r in results:
            tid = r["metric"].get("tenant_id", "")
            name = r["metric"].get("tenant", "")
            if tid and name:
                id_by_name[name] = tid

        tenant_task: dict[str, dict] = {}
        for r in results:
            ep = r["metric"].get(PROMETHEUS_API_PATH_LABEL, "")
            tenant_id_label = r["metric"].get("tenant_id", "")
            tenant_label = r["metric"].get("tenant", "")
            task = cls._resolve_task_key(ep)
            if task not in active_services:
                continue
            v = max(0, round(float(r["value"][1])))
            if v <= 0:
                continue
            resolved_id = tenant_id_label or id_by_name.get(tenant_label, "")
            key = resolved_id or f"name:{tenant_label}"
            bucket = tenant_task.setdefault(
                key, {"tenant_id": resolved_id, "tenant": tenant_label, "tasks": {}}
            )
            if tenant_label:
                bucket["tenant"] = tenant_label
            bucket["tasks"][task] = bucket["tasks"].get(task, 0) + v
        return tenant_task

    @staticmethod
    def _rank_tenants_by_total(
        tenant_task: dict[str, dict]
    ) -> list[tuple[dict, int]]:
        """(bucket, total) sorted by total descending."""
        return sorted(
            [(bucket, sum(bucket["tasks"].values())) for bucket in tenant_task.values()],
            key=lambda x: x[1],
            reverse=True,
        )

    def _heatmap_row(
        self,
        rank: int,
        tenant_label: str,
        total: int,
        tasks: dict[str, int],
        active_services: list[str],
        grand_total: int,
    ) -> dict:
        return {
            "rank": rank,
            "tenant": tenant_label,
            "services": {
                svc: {
                    "display_name": SERVICE_BREAKDOWN_CONFIG[svc]["display_name"],
                    "requests": tasks.get(svc, 0),
                    "formatted_requests": self._format_count(tasks.get(svc, 0)),
                    # share of THIS tenant's total (row-wise %)
                    "percentage": round(tasks.get(svc, 0) / total * 100, 1) if total else 0.0,
                }
                for svc in active_services
            },
            "total": total,
            "formatted_total": self._format_count(total),
            # this tenant's share of all tenants' total (grand-total %)
            "percentage": round(total / grand_total * 100, 1) if grand_total else 0.0,
        }

    async def usage_by_tenant_service(
        self,
        limit: int,
        time_range: Optional[str],
        services: Optional[list[str]],
        tenant: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> dict:
        """Heatmap matrix: top-N tenants × per-service request counts.

        Uses a single sum by(tenant_id, tenant, exported_endpoint) query with
        offset subtraction (same approach as service_breakdown) to avoid
        increase() extrapolation errors. ``tenant`` rides alongside
        ``tenant_id`` in the group-by so a pre-cutover row (empty tenant_id)
        still carries a usable name; _accumulate_tenant_task_counts then
        re-buckets by tenant_id (falling back to name only when empty) so a
        same-window rename doesn't split a tenant's traffic across two
        buckets. When ``tenant_id`` (or ``tenant``) is given, the matrix is
        scoped to that single tenant.

        KNOWN CUTOVER GAP when ``tenant_id`` (or ``tenant``) scopes the
        matrix to one tenant: see build_base_selectors' docstring —
        accepted, not fixed here, tracked in the ticket. The unscoped
        top-N matrix (no tenant_id/tenant filter) is unaffected.
        """
        active_services = services or list(SERVICE_BREAKDOWN_CONFIG)

        _ep = f'{PROMETHEUS_API_PATH_LABEL}=~"{SERVICE_BREAKDOWN_ENDPOINT_REGEX}"'
        _tenant_part = (
            f',tenant_id="{escape_label_value(tenant_id)}"' if tenant_id
            else (f',tenant="{escape_label_value(tenant)}"' if tenant else '')
        )
        base_sel = '{' + _ep + ',tenant!="unknown"' + _tenant_part + ',' + api_key_auth_type_selector() + '}'
        metric = f"{_METRIC}{base_sel}"
        window = TIME_RANGES.get(time_range or "all")

        if window:
            promql = (
                f"sum by(tenant_id, tenant, {PROMETHEUS_API_PATH_LABEL}) ("
                f"({metric} unless {metric} offset {window})"
                f" or (increase({metric}[{window}]) > 0)"
                f") > 0"
            )
        else:
            promql = f"sum by(tenant_id, tenant, {PROMETHEUS_API_PATH_LABEL}) ({metric}) > 0"

        results = await self._client.query(promql)
        tenant_task = self._accumulate_tenant_task_counts(results, active_services)
        ranked = self._rank_tenants_by_total(tenant_task)
        grand_total = sum(total for _, total in ranked)
        top = ranked[:limit]
        names = await self._resolve_tenant_names(
            {bucket["tenant_id"] for bucket, _ in top if bucket["tenant_id"]}
        )

        rows = [
            self._heatmap_row(
                idx + 1,
                names.get(bucket["tenant_id"], "") or bucket["tenant"] or bucket["tenant_id"] or "unknown",
                total, bucket["tasks"], active_services, grand_total,
            )
            for idx, (bucket, total) in enumerate(top)
        ]

        return {
            "tenants": rows,
            "services": [
                {"key": svc, "display_name": SERVICE_BREAKDOWN_CONFIG[svc]["display_name"]}
                for svc in active_services
            ],
            "grand_total": grand_total,
            "formatted_grand_total": self._format_count(grand_total),
            "total_tenant_count": len(ranked),
            "filters": {
                "limit": limit,
                "time_range": time_range or "all",
                "services": active_services,
            },
        }

    # ── private helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _safe(result, default):
        """Return `result` unless the gather() call raised — then `default`."""
        return default if isinstance(result, Exception) else result

    @staticmethod
    def _service_breakdown_by_ep_promql(selector: str, window: Optional[str]) -> str:
        """PromQL for one service_breakdown selector, grouped by endpoint.

        Without a window: a plain instantaneous sum. With one: an
        offset-diff that's reset-aware, falling back to increase() for
        brand-new series — same reasoning as the native-unit queries below.
        """
        metric = f"{_METRIC}{selector}"
        if not window:
            return f"sum by({PROMETHEUS_API_PATH_LABEL}) ({metric})"
        return (
            f"sum by({PROMETHEUS_API_PATH_LABEL}) ("
            f"({metric} unless {metric} offset {window})"
            f" or (increase({metric}[{window}]) > 0)"
            f")"
        )

    def _native_unit_queries(
        self, tenant: Optional[str], time_range: Optional[str],
        service_filter: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> tuple[list[str], list]:
        """Per-service native-unit scalar query coroutines — one per task
        that has a real Prometheus Histogram _sum metric (SERVICE_BREAKDOWN_CONFIG).

        service_filter (the frontend's enabled-task-type allowlist), when
        given, skips the native-unit query entirely for excluded tasks —
        a query-level reduction, not just a display-level one.

        These native-unit metrics (tts/nmt/asr/... characters/minutes) now
        carry a ``tenant_id`` label alongside ``tenant`` (see metrics.py) —
        ``tenant_id`` is preferred over ``tenant`` when given, same
        precedence as build_base_selectors, so this stays correct across a
        tenant rename instead of silently returning platform-wide numbers.

        KNOWN CUTOVER GAP when ``tenant_id`` is given: see
        build_base_selectors' docstring — accepted, not fixed here, tracked
        in the ticket.
        """
        native_tasks: list[str] = []
        native_coros = []
        for task, cfg in SERVICE_BREAKDOWN_CONFIG.items():
            if service_filter is not None and task not in service_filter:
                continue
            native_metric = cfg.get("native_metric")
            if not native_metric:
                continue
            extra = cfg.get("native_extra_labels") or []
            if tenant_id:
                parts = [f'tenant_id="{escape_label_value(tenant_id)}"']
            elif tenant:
                parts = [f'tenant="{escape_label_value(tenant)}"']
            else:
                parts = []
            parts.append(api_key_auth_type_selector())
            parts.extend(extra)
            sel = "{" + ",".join(parts) + "}" if parts else ""
            # Use increase()-based counting (via sum_over_window), NOT a raw
            # `sum(now) - sum(offset)` delta. The histogram _sum is a counter that
            # resets on pod restart; a raw delta goes negative across a restart and
            # gets dropped by the `v > 0` guard, so native units flicker in and out
            # ("sometimes shows, sometimes not"). increase() is reset-aware and also
            # handles brand-new series — matching how request counts are computed.
            q = sum_over_window(f"{native_metric}{sel}", time_range)
            native_tasks.append(task)
            native_coros.append(self._client.scalar(q))
        return native_tasks, native_coros

    @staticmethod
    def _unpack_native_units(native_tasks: list[str], raw: list, native_offset: int) -> dict:
        """Map task key → rounded native-unit value from the gather() results.

        A 0.0 result means either no usage occurred or the metric doesn't
        exist yet (the `or vector(0)` fallback fires) — both legitimately report 0.
        """
        natives: dict = {}
        for i, task in enumerate(native_tasks):
            v = MeteringService._safe(raw[native_offset + i], None)
            if v is not None:
                # Audio-minutes metrics keep 2-decimal precision (a 60-second
                # rounding step would erase sub-minute usage); everything else
                # (characters/tokens/images) rounds to a whole unit.
                cfg = SERVICE_BREAKDOWN_CONFIG[task]
                natives[task] = round(v, 2) if cfg.get("round_2dp") else round(v)
        return natives

    def _model_native_unit_queries(
        self, tenant: Optional[str], tenant_id: Optional[str], time_range: Optional[str],
        task_types: Optional[list[str]],
    ) -> tuple[list[str], list]:
        """Per-task-type native-unit query coroutines for model_breakdown.

        Same selector precedence and task-metric config as
        `_native_unit_queries` (service_breakdown's own version), but grouped
        by `service_id` — every row here needs its OWN native-unit value,
        not one tenant-wide scalar — via `query()`, not `scalar()`.
        `task_types`, when given, restricts to just those tasks (same
        ghost-avoidance reasoning `model_breakdown` already applies to its
        request-count queries); `None` covers every SERVICE_BREAKDOWN_CONFIG
        task that has a native metric.

        Always excludes ``tenant="unknown"`` — the same guard
        `build_base_selectors` applies to `total_q`/`success_q` above. Without
        it, the all-tenants view would count unresolved-tenant traffic in
        `native_units` that the request counts exclude, AND a service whose
        only in-window traffic has no resolved tenant could enter
        `service_ids` purely via this native vector with 0 requests and an
        unresolved `task_type` — exactly the row shape the FE's Zod schema
        rejects the whole response over (native_unit_suffix must stay a
        string on the wire, never null).
        """
        native_tasks: list[str] = []
        native_coros = []
        for task, cfg in SERVICE_BREAKDOWN_CONFIG.items():
            if task_types is not None and task not in task_types:
                continue
            native_metric = cfg.get("native_metric")
            if not native_metric:
                continue
            extra = cfg.get("native_extra_labels") or []
            parts = ['tenant!="unknown"']
            if tenant_id:
                parts.append(f'tenant_id="{escape_label_value(tenant_id)}"')
            elif tenant:
                parts.append(f'tenant="{escape_label_value(tenant)}"')
            parts.append(api_key_auth_type_selector())
            parts.extend(extra)
            sel = "{" + ",".join(parts) + "}" if parts else ""
            q = sum_over_window_by(f"{native_metric}{sel}", "service_id", time_range)
            native_tasks.append(task)
            native_coros.append(self._client.query(q))
        return native_tasks, native_coros

    @staticmethod
    def _native_units_by_service(rows: list) -> dict[str, float]:
        """Map service_id -> raw (unrounded) native-unit value from a `sum
        by(service_id)` result vector. One row per service_id — rounding is
        deferred to the caller since the correct precision (whole unit vs
        2dp for audio-minutes) depends on which task the SERVICE consuming
        this value belongs to, not the metric itself."""
        return {
            r["metric"].get("service_id", ""): float(r["value"][1])
            for r in rows
        }

    @staticmethod
    def _metering_cfg_for_task(task: Optional[str]) -> Optional[dict]:
        """SERVICE_BREAKDOWN_CONFIG entry for a metering task key (e.g.
        "nmt", "audio_language_detection"), or None when there isn't one
        (unknown task, or no task resolved for the row at all — see
        service_task/model_task in model_breakdown)."""
        if not task:
            return None
        return SERVICE_BREAKDOWN_CONFIG.get(task)

    @classmethod
    def _round_native(
        cls, task: Optional[str], raw_value: float, unit_map: dict[str, str]
    ) -> tuple[float, str]:
        """Round an already-aggregated native-unit value per its task's
        `round_2dp` config, returning (value, unit_suffix). `unit_suffix` is
        never None/empty — see `_native_unit_suffix_for_metering_task` — a
        0.0 value alongside its generic fallback suffix is how an
        unknown/unmapped task is represented on the wire."""
        cfg = cls._metering_cfg_for_task(task)
        rounded = round(raw_value, 2) if cfg and cfg.get("round_2dp") else round(raw_value)
        return float(rounded), _native_unit_suffix_for_metering_task(task, unit_map)

    @classmethod
    def _native_units_for(
        cls, task: Optional[str],
        native_by_task: dict[str, dict[str, float]], service_id: str,
        unit_map: dict[str, str],
    ) -> tuple[float, str]:
        """(native_units, native_unit_suffix) for one service row, picking
        its value out of `native_by_task` by its own task."""
        raw_value = native_by_task.get(task, {}).get(service_id, 0.0) if task else 0.0
        return cls._round_native(task, raw_value, unit_map)

    @staticmethod
    def _service_breakdown_rows(
        totals: dict, successes: dict, natives: dict,
        unit_map: dict[str, str],
        service_filter: Optional[list[str]] = None,
    ) -> list:
        """Assemble + sort the per-service rows from the three unpacked dicts.

        service_filter (the frontend's enabled-task-type allowlist), when
        given, excludes rows for tasks not in it."""
        services = []
        for task, cfg in SERVICE_BREAKDOWN_CONFIG.items():
            if service_filter is not None and task not in service_filter:
                continue
            total_v = totals.get(task, 0)
            success_v = successes.get(task, 0)
            services.append({
                "service": cfg["display_name"],
                "requests": total_v,
                "native_units": natives.get(task, 0),
                "native_unit_suffix": _native_unit_suffix_for_metering_task(task, unit_map),
                "success_pct": round(success_v / total_v * 100, 2) if total_v else 0.0,
            })
        services.sort(key=lambda s: s["requests"], reverse=True)
        return services

    @staticmethod
    def _endpoint_dict(results: list) -> dict:
        """Map task key → rounded value from a `sum by(exported_endpoint)` result vector.

        Handles two endpoint patterns:
          - Standard: /api/v1/{task}/inference  → task = path segment at index 2
          - Non-standard: looked up via ENDPOINT_TO_TASK (e.g. /api/v1/chat → llm)
        """
        out: dict = {}
        for r in results:
            ep = r["metric"].get(PROMETHEUS_API_PATH_LABEL, "")
            task = ENDPOINT_TO_TASK.get(ep)
            if task is None:
                parts = [p for p in ep.split("/") if p]
                # /api/v1/{task}/inference → ['api', 'v1', task, 'inference']
                # Normalise hyphens to underscores so speaker-diarization → speaker_diarization
                raw = parts[2] if len(parts) >= 4 else ep
                task = raw.replace("-", "_")
            out[task] = out.get(task, 0) + round(float(r["value"][1]))
        return out

    @staticmethod
    def _label_dict(results: list, key) -> dict:
        """Map a resolved key -> rounded sum from a `sum by(...)` result vector.

        `key` is either a Prometheus label name (str) — extracted via
        `metric.get(key, "")` — or a callable `row -> str` for a key that
        isn't a single literal label (e.g. model_breakdown's effective-
        model_id fallback, which needs more than one label on the row to
        resolve). Keeping the rounding/summing loop here in one place, used
        by both forms, avoids that logic drifting between two copies.
        """
        resolve = key if callable(key) else (lambda r: r["metric"].get(key, ""))
        out: dict = {}
        for r in results:
            k = resolve(r)
            out[k] = out.get(k, 0) + round(float(r["value"][1]))
        return out

    @staticmethod
    def _format_count(n: int) -> str:
        """Human-readable request count: 1250000 → '1.25M', 973100 → '973.1K'."""
        if n >= 1_000_000:
            s = f"{n / 1_000_000:.2f}".rstrip("0").rstrip(".")
            return f"{s}M"
        if n >= 1_000:
            s = f"{n / 1_000:.1f}".rstrip("0").rstrip(".")
            return f"{s}K"
        return str(n)

    @staticmethod
    def _tenant_delta_promql(metric: str, time_range: Optional[str]) -> str:
        # Groups by tenant (the name) alongside tenant_id so a pre-cutover
        # row (empty tenant_id) still carries a usable name instead of being
        # merged into one anonymous bucket — see _merge_tenant_rows, which
        # re-merges same-tenant_id rows so a same-window rename (which now
        # produces two rows sharing one tenant_id) doesn't split back apart.
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return f"sum by(tenant_id, tenant) ({metric}) > 0"
        return (
            f"sum by(tenant_id, tenant) ("
            f"({metric} unless {metric} offset {window})"
            f" or (increase({metric}[{window}]) > 0)"
            f") > 0"
        )

    @staticmethod
    def _by_tenant_promql(metric: str, time_range: Optional[str], filter_zero: bool) -> str:
        # See _tenant_delta_promql above for why `tenant` rides alongside
        # `tenant_id` in the group-by.
        window = TIME_RANGES.get(time_range or "all")
        if window:
            return (
                f"sum by(tenant_id, tenant) ("
                f"({metric} unless {metric} offset {window})"
                f" or (increase({metric}[{window}]) > 0)"
                f") > 0"
            )
        base = f"sum by(tenant_id, tenant) ({metric})"
        return f"{base} > 0" if filter_zero else base

    @staticmethod
    def _merge_tenant_rows(rows: list) -> list[dict]:
        """Re-merge Prometheus rows already grouped by (tenant_id, tenant)
        back into one entry per real tenant.

        _by_tenant_promql/_tenant_delta_promql group by BOTH labels so a
        pre-cutover row (empty tenant_id) still carries a usable tenant name
        instead of being dropped. That means the SAME active tenant produces
        two rows for as long as its traffic spans the cutover: an old row
        with no tenant_id, and a new one with it — both carrying the same
        ``tenant`` name. A first pass learns tenant_id from whichever rows
        already have one (name -> id), so the second pass can fold a
        no-id row into that same tenant's bucket by matching its name,
        instead of keying it "name:<x>" and creating a second, unmergeable
        entry for a tenant that already has an id. (A tenant renamed AND
        spanning the cutover — no id-bearing row shares its old name — still
        can't be unified this way; that's a real, accepted gap, not this
        function's bug, since there's no rename history to match on. It's
        also the same rare-overlap assumption that a name uniquely
        identifies one tenant relies on: two distinct tenants that happen to
        share an org name would incorrectly fold together here.)
        """
        # Pass 1: which tenant_id does each name currently belong to?
        id_by_name: dict[str, str] = {}
        for r in rows:
            tid = r["metric"].get("tenant_id", "")
            name = r["metric"].get("tenant", "")
            if tid and name:
                id_by_name[name] = tid

        # Pass 2: merge, resolving a missing tenant_id via the name lookup
        # above before falling back to a name-only bucket.
        merged: dict[str, dict] = {}
        for r in rows:
            tid = r["metric"].get("tenant_id", "")
            name = r["metric"].get("tenant", "")
            resolved_id = tid or id_by_name.get(name, "")
            key = resolved_id or f"name:{name}"
            value = float(r["value"][1])
            entry = merged.get(key)
            if entry is None:
                merged[key] = {"tenant_id": resolved_id, "tenant": name, "value": value}
            else:
                entry["value"] += value
                if name:
                    entry["tenant"] = name
        return list(merged.values())

    async def _fetch_valid_tenant_ids(self) -> Optional[set]:
        """Return the set of currently-ACTIVE tenant ids (as strings) from the auth DB.

        Prometheus results are grouped/filtered by ``tenant_id`` (immutable —
        see ai4i_core.observability.middleware), so validity must be checked
        against that same value rather than the organisation name, which
        changes on a rename. Restricted to status='ACTIVE' so PENDING/
        SUSPENDED/DEACTIVATED tenants — who can't currently authenticate (see
        APIKeyService.user_may_use_api_keys) but may still have in-window
        Prometheus series from before their status changed — don't inflate
        the Active Tenants count on the Usage Dashboard.
        Returns None when the auth DB is unavailable so callers fall back to
        unfiltered Prometheus results rather than returning an empty count.
        """
        if self._auth_db is None:
            return None
        try:
            rows = await self._auth_db.execute(
                text("SELECT id FROM tenants WHERE status = 'ACTIVE'")
            )
            return {str(r[0]) for r in rows.all()}
        except Exception:
            logger.warning("_fetch_valid_tenant_ids: auth DB query failed", exc_info=True)
            await self._safe_rollback_auth_db()
            return None

    async def _resolve_tenant_names(self, tenant_ids: set) -> dict:
        """Batch-resolve tenant_id -> current organisation name for display.

        Prometheus results are grouped by tenant_id so counts stay correct
        across a rename (see _by_tenant_promql/_tenant_delta_promql); this
        fills in whatever the organisation is named *right now* for the UI,
        rather than showing the raw id. Empty/falsy ids (series from before
        the tenant_id label existed, or "unknown") and non-numeric ids
        (auth-service tolerates non-numeric tenant ids elsewhere) are
        skipped rather than passed to int(), so one bad id can't fail the
        whole batch. Returns {} (never None) on a DB miss so callers can
        always call .get() safely — the raw id/label is still shown as a
        fallback, just not the name.
        """
        ids = {tid for tid in tenant_ids if tid and tid.isdigit()}
        if self._auth_db is None or not ids:
            return {}
        try:
            rows = await self._auth_db.execute(
                text("SELECT id, organisation FROM tenants WHERE id = ANY(:ids)"),
                {"ids": [int(tid) for tid in ids]},
            )
            return {str(r[0]): r[1] for r in rows.all()}
        except Exception:
            logger.warning("_resolve_tenant_names: auth DB query failed", exc_info=True)
            await self._safe_rollback_auth_db()
            return {}
