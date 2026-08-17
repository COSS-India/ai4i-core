"""Metering business logic — PromQL construction, Prometheus calls, result shaping."""
import asyncio
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.model_management.model_repository import ModelRepository
from app.repositories.model_management.service_repository import ServiceRepository
from app.utils.prometheus_client import PrometheusClient
from app.utils.metering_promql_builder import (
    TIME_RANGES,
    SERVICE_BREAKDOWN_CONFIG,
    SERVICE_BREAKDOWN_ENDPOINT_REGEX,
    LLM_CHAT_ENDPOINT_REGEX,
    ENDPOINT_TO_TASK,
    PROMETHEUS_API_PATH_LABEL,
    build_base_selectors,
    build_task_type_selector,
    escape_label_value,
    sum_over_window,
    sum_over_window_by,
)

logger = logging.getLogger(__name__)

_METRIC = "telemetry_obsv_requests_total"


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

    # ── public methods ──────────────────────────────────────────────────────

    async def request_total(
        self,
        inference_only: bool,
        tenant: Optional[str],
        service_id: Optional[str],
        time_range: Optional[str],
        task_types: Optional[list[str]] = None,
    ) -> dict:
        task_sel = build_task_type_selector(task_types)
        extra = [task_sel] if task_sel else None
        success_extra = [task_sel, 'status_code=~"2.."'] if task_sel else ['status_code=~"2.."']
        label_str = build_base_selectors(inference_only, tenant, service_id, extra=extra)
        success_label_str = build_base_selectors(
            inference_only, tenant, service_id, extra=success_extra
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

    async def active_tenants(self, time_range: Optional[str]) -> dict:
        """
        ROLLOUT NOTE: the ``tenant`` label switched from the numeric tenant id
        to the organisation name (see ObservabilityMiddleware). Existing
        Prometheus series from before the cutover still carry the id, which
        never matches ``valid_names`` (current organisation names) below, so
        any query window spanning the cutover undercounts — pre-cutover,
        id-labelled series are dropped even though real traffic occurred.
        This self-heals as pre-cutover series age out of the window (1h/24h
        clear within a day; 7d/30d take up to 7/30 days). There is no
        after-the-fact fix: Prometheus relabeling only applies at scrape time
        to a target's own labels, it cannot rewrite already-stored series to
        translate an id to the org name it corresponded to at write time.
        """
        metric = f"{_METRIC}{build_base_selectors(inference_only=True)}"
        promql = self._by_tenant_promql(metric, time_range, filter_zero=True)
        prom_results, valid_names = await asyncio.gather(
            self._client.query(promql),
            self._fetch_valid_tenant_names(),
        )
        # Filter Prometheus results to only tenants that are currently ACTIVE
        # in the DB. Without this, deleted tenants (or tenants that are no
        # longer ACTIVE) whose Prometheus series are still within the
        # retention window inflate the count.
        tenants = [
            {
                "tenant": r["metric"].get("tenant", "unknown"),
                "request_count": int(float(r["value"][1])),
            }
            for r in prom_results
            if valid_names is None or r["metric"].get("tenant") in valid_names
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
        """
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return None
        metric = f"{_METRIC}{build_base_selectors(inference_only=True)}"
        promql = f"count(sum by(tenant)(increase({metric}[{window}] offset {window}) > 0))"
        try:
            return int(round(float(await self._client.scalar(promql))))
        except Exception:
            return None

    async def avg_per_active_tenant_previous(
        self, time_range: Optional[str], tenant: Optional[str] = None
    ) -> Optional[int]:
        """Avg requests per active tenant in the PREVIOUS window (offset by one
        window) — same offset pattern as request_total's prev counts. Drives the
        Avg-Requests-Per-Tenant trend. None when unbounded or no prior activity."""
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return None
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, tenant=tenant)}"
        total_q = f"sum(increase({metric}[{window}] offset {window}))"
        active_q = f"count(sum by(tenant)(increase({metric}[{window}] offset {window}) > 0))"
        try:
            total, active = await asyncio.gather(
                self._client.scalar(total_q), self._client.scalar(active_q)
            )
            if total is None or active is None:
                return None  # no prior-window data — not an error
            total_v, active_v = float(total), float(active)
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
            new_tenants = await self._auth_db.execute(
                text("SELECT COUNT(*) FROM tenants WHERE created_at >= NOW() - INTERVAL '7 days'")
            )
            return {
                "total_tenants": total.scalar(),
                "new_tenants": new_tenants.scalar(),
                "auth_db_available": True,
            }
        except Exception:
            logger.warning("tenant_count: auth DB query failed", exc_info=True)
            return {
                "total_tenants": None,
                "new_tenants": None,
                "auth_db_available": False,
            }

    async def usage_concentration(
        self, limit: int, time_range: Optional[str], task_types: Optional[list[str]] = None,
    ) -> dict:
        task_sel = build_task_type_selector(task_types)
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, extra=[task_sel] if task_sel else None)}"
        promql = self._by_tenant_promql(metric, time_range, filter_zero=False)
        results = await self._client.query(promql)

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
    ) -> dict:
        """Per-service stats: requests, native units, success %, failed, vs prev period.

        Fires all Prometheus queries in a single asyncio.gather:
          - 4–5 endpoint-grouped queries for request counts / prev period
          - 1 scalar query per service that has a dedicated native-unit metric
        """
        # Use the broader regex so /api/v1/chat (LLM) is included alongside
        # the standard /api/v1/{task}/inference endpoints.
        _ep = f'{PROMETHEUS_API_PATH_LABEL}=~"{SERVICE_BREAKDOWN_ENDPOINT_REGEX}"'
        _base = _ep + ',tenant!="unknown"' + (f',tenant="{escape_label_value(tenant)}"' if tenant else "")
        base_sel    = "{" + _base + "}"
        success_sel = "{" + _base + ',status_code=~"2.."' + "}"

        window = TIME_RANGES.get(time_range or "all")

        fixed_queries = [
            self._client.query(self._service_breakdown_by_ep_promql(base_sel, window)),     # 0 total
            self._client.query(self._service_breakdown_by_ep_promql(success_sel, window)),  # 1 success
        ]
        native_tasks, native_coros = self._native_unit_queries(tenant, time_range, service_filter)

        raw = await asyncio.gather(*fixed_queries, *native_coros, return_exceptions=True)

        totals = self._endpoint_dict(self._safe(raw[0], []))
        successes = self._endpoint_dict(self._safe(raw[1], []))
        natives = self._unpack_native_units(native_tasks, raw, native_offset=len(fixed_queries))

        return {
            "services": self._service_breakdown_rows(totals, successes, natives, service_filter),
            "filters": {"tenant": tenant, "time_range": time_range or "all"},
        }

    async def model_breakdown(self, tenant: Optional[str], time_range: Optional[str]) -> dict:
        """Per-service LLM usage: requests, tokens, success %, grouped by
        `service_id` — the tenant-facing service the client called (the
        OpenAI `model` field as sent), NOT the `model` Prometheus label.

        The `model` label (the real upstream model echoed back by the
        inference engine) is intentionally not grouped or filtered on here:
        one service maps to exactly one model, but many services can share
        the same underlying model, so grouping by model would merge
        distinct services' traffic and destroy tenant attribution. See
        model-consumption-api-highlevel-design.md §1/§5. Each row's
        `model_name` (informational only) is resolved via a batched
        mm_services -> mm_models DB lookup (mm_services.model_id is an
        opaque hash, not a display name — see
        ServiceRepository.get_names_and_models_by_service_ids), not from
        Prometheus — the `model` label is absent on failed requests and can
        differ between the buffered and streaming response paths for the
        same service.

        Fires 3 queries in one asyncio.gather: total requests, successful
        requests, and tokens processed — each grouped by `service_id`.

        ROLLOUT NOTE: rows are cross-checked against the Service Registry
        (mm_services) via that same lookup, and a `service_id` with no
        current, non-deleted row is dropped. Two different populations land
        here: `service_id` is the client-supplied `model` string, set before
        MMS resolution, so a request for a service that was deleted/renamed
        OR one that never existed (a typo, a stale integration still
        pointing at an old id — the `llm`/`llm/default` cases) both emit
        Prometheus series but neither has a current registry row. We can't
        tell those apart here, so both are dropped — which means, unlike the
        never-existed case, a rename/delete makes this endpoint
        under-report real historical traffic for up to `time_range` (30d)
        against Overview's `request_total`, which is NOT registry-filtered
        (see routes/metering.py `request_total(service_id=None, ...)`) and
        keeps counting it. This self-heals as the pre-rename/delete series
        age out of the window, the same tradeoff `active_tenants` makes for
        the tenant-id -> org-name cutover (see its ROLLOUT NOTE above). The
        check is skipped (all ids kept, name falls back to the raw id) only
        when the registry lookup itself is unavailable or errors — we can't
        tell "deleted" from "DB unreachable" in that case. Suppressed ids
        are logged (see below) so a rename-induced drop is traceable rather
        than a silent discrepancy against Overview.
        """
        base_sel = build_base_selectors(
            inference_only=True, tenant=tenant, endpoint_regex=LLM_CHAT_ENDPOINT_REGEX
        )
        success_sel = build_base_selectors(
            inference_only=True, tenant=tenant, endpoint_regex=LLM_CHAT_ENDPOINT_REGEX,
            extra=['status_code=~"2.."'],
        )
        tokens_parts = ['token_type="total"', 'tenant!="unknown"']
        if tenant:
            tokens_parts.append(f'tenant="{escape_label_value(tenant)}"')
        tokens_sel = "{" + ",".join(tokens_parts) + "}"

        total_q = sum_over_window_by(f"{_METRIC}{base_sel}", "service_id", time_range)
        success_q = sum_over_window_by(f"{_METRIC}{success_sel}", "service_id", time_range)
        tokens_q = sum_over_window_by(
            f"telemetry_obsv_llm_tokens_processed_sum{tokens_sel}", "service_id", time_range
        )

        raw = await asyncio.gather(
            self._client.query(total_q),
            self._client.query(success_q),
            self._client.query(tokens_q),
            return_exceptions=True,
        )

        def _safe_list(r):
            return r if not isinstance(r, Exception) else []

        totals = self._label_dict(_safe_list(raw[0]), "service_id")
        successes = self._label_dict(_safe_list(raw[1]), "service_id")
        tokens = self._label_dict(_safe_list(raw[2]), "service_id")

        # "" means the client sent no `model` field at all — not a real service.
        service_ids = {s for s in (set(totals) | set(successes) | set(tokens)) if s != ""}

        names_and_models: dict = {}
        registry_checked = False
        if self._service_repo is not None and service_ids:
            try:
                names_and_models = await self._service_repo.get_names_and_models_by_service_ids(
                    list(service_ids)
                )
                registry_checked = True
            except Exception:
                logger.warning("model_breakdown: service name/model lookup failed", exc_info=True)

        # service_id with no current, non-deleted mm_services row: either a
        # genuinely deleted/renamed service (real historical traffic — see
        # the ROLLOUT NOTE above) or one that never existed (a typo / stale
        # integration, e.g. "llm", "llm/default"). Only computed when the
        # registry lookup actually ran — if it's unavailable/failed we can't
        # tell "deleted" from "DB down", so nothing is dropped.
        ghosts = (service_ids - names_and_models.keys()) if registry_checked else set()
        if ghosts:
            logger.info(
                "model_breakdown: dropped %d unregistered service_id(s): %s",
                len(ghosts), sorted(ghosts),
            )

        services = []
        for service_id in service_ids:
            if service_id in ghosts:
                continue
            total_v = totals.get(service_id, 0)
            success_v = successes.get(service_id, 0)
            name, model_name = names_and_models.get(service_id, (service_id, None))
            services.append({
                "service_id": service_id,
                "name": name,
                "model_name": model_name,
                "requests": total_v,
                "native_units": float(tokens.get(service_id, 0)),
                "success_pct": round(success_v / total_v * 100, 2) if total_v else 0.0,
            })

        services.sort(key=lambda s: s["requests"], reverse=True)

        return {
            "services": services,
            "filters": {"tenant": tenant, "time_range": time_range or "all"},
        }

    async def registry_model_count(self) -> Optional[int]:
        """Distinct models currently registered in the Registry — see
        ModelRepository.count_distinct_models for why this is a distinct
        (case-insensitive) model-name count, spanning both ACTIVE and
        DEPRECATED versions, rather than a raw `mm_models` row count (which
        would over-count a model with several versions).

        Not tenant-scoped: ``mm_models`` has no tenant column — the Registry is
        a shared catalog, not partitioned per institution — so this value is
        the same platform-wide regardless of the caller's tenant_id. Returns
        None (never raises) when the DB is unavailable, same pattern as
        tenant_count(), so a Registry lookup failure degrades this one summary
        field instead of the whole response.
        """
        if self._model_repo is None:
            return None
        try:
            return await self._model_repo.count_distinct_models()
        except Exception:
            logger.warning("registry_model_count: DB query failed", exc_info=True)
            return None

    @staticmethod
    def _model_identity(model_name: str) -> str:
        """Case-fold a resolved `model_name` into the grouping key used
        everywhere a model is counted/aggregated in this file — matches
        generate_model_id's own identity rule (name is lower-cased before
        hashing; see app/utils/hashing.py), so "Gemma" and "gemma" are always
        treated as the same model, never as two."""
        return model_name.casefold()

    @staticmethod
    def model_consumption_ranking(
        services: list[dict], limit: int
    ) -> tuple[Optional[dict], list[dict], int]:
        """Aggregate the service-level rows from `model_breakdown` up to
        model-level, for the Model Consumption summary's `most_used` KPI and
        the `top_models` ranking (AI4IDS-2790).

        Only services with a RESOLVED `model_name` are counted — the same
        population `model_consumption_kpis`'s `active_models` counts. A
        service whose model lookup failed isn't an identifiable Registry
        model, so it can't be one on this ranking either; it still appears
        in the raw per-service `breakdown` list, just not here. Because of
        that, the `grand_total` this returns is NOT the full window's total
        requests — it's the sum over resolved-model services only, which is
        also the denominator `consumption_pct` is computed against. Callers
        must surface this `grand_total` (not some other "total requests"
        figure) alongside `consumption_pct`, or the percentages won't add up
        against whatever total gets displayed next to them.

        consumption_pct per model = this model's total requests / grand_total
        * 100 — its SHARE of total requests among resolved-model services.
        A model backed by >1 service is the SUM of those services' requests
        (equivalently, the sum of their individual shares) — not an average —
        which keeps two things true:
          - consumption_pct values sum to ~100% across the full ranked list
            (small drift from the 2dp rounding on each row — e.g. three
            equal-traffic models give 33.33 x 3 = 99.99, not a bug), and
          - `most_used` and `top_models[0]` always name the same model, since
            both rank on total requests (dividing by the same grand_total
            preserves order).

        Returns (most_used, ranked, grand_total) — most_used/ranked are
        None/[] when there's no traffic from any resolved-model service;
        grand_total is always an int (0 in that case).
        """
        active = [s for s in services if s["requests"] > 0 and s.get("model_name")]
        grand_total = sum(s["requests"] for s in active)
        if not active or not grand_total:
            return None, [], 0

        groups: dict[str, dict] = {}
        for s in active:
            key = MeteringService._model_identity(s["model_name"])
            # First-seen casing wins the display name — so "Gemma" and "gemma"
            # (two versions saved with different casing) merge into one row
            # instead of splitting the same model's traffic across two.
            g = groups.setdefault(key, {"model_name": s["model_name"], "requests": 0})
            g["requests"] += s["requests"]

        ranked = sorted(
            (
                {
                    "model_name": g["model_name"],
                    "requests": g["requests"],
                    "consumption_pct": round(g["requests"] / grand_total * 100, 2),
                }
                for g in groups.values()
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
    def model_consumption_kpis(services: list[dict]) -> dict:
        """Scalar KPIs for the Model Consumption summary (AI4IDS-2790), computed
        over services with traffic (`requests > 0`):

        - `active_models`: count of DISTINCT resolved Registry model names
          (case-folded — see `_model_identity`) — the same population
          `model_consumption_ranking` groups by (a service whose model
          lookup failed isn't a model here either). Always an int; 0 (not
          None) when there's no traffic at all — 0 is itself a real,
          meaningful answer ("no models were active"), unlike
          `overall_success_rate_pct`, which is genuinely undefined with no
          data to average.
        - `overall_success_rate_pct`: REQUEST-WEIGHTED success rate — sum(
          requests * success_pct) / sum(requests) — matching the FE's
          existing (previously dormant) fallback formula, so this field
          doesn't silently change what the dashboard already shows once
          populated. Deliberately a WIDER population than `active_models`/
          the ranking: it's computed over every service with traffic,
          INCLUDING ones whose model lookup failed, since success/failure is
          a traffic-health signal independent of whether the model behind it
          was identifiable. None when there's no traffic to average over.
        - `worst`: the active service with the highest failure rate — raw
          dict, consumed by the caller to build `highest_failure_rate`
          (which stays service-level, not aggregated to model-level). None
          when there's no traffic.
        """
        active = [s for s in services if s["requests"] > 0]
        active_models = len(
            {MeteringService._model_identity(s["model_name"]) for s in active if s.get("model_name")}
        )
        total_requests = sum(s["requests"] for s in active)
        overall_success_rate_pct = (
            round(sum(s["requests"] * s["success_pct"] for s in active) / total_requests, 2)
            if total_requests else None
        )
        worst = max(active, key=lambda s: 100 - s["success_pct"]) if active else None
        return {
            "active_models": active_models,
            "overall_success_rate_pct": overall_success_rate_pct,
            "worst": worst,
        }

    async def tenant_ranking(
        self, limit: int, time_range: Optional[str], tenant: Optional[str] = None
    ) -> dict:
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, tenant=tenant)}"
        promql = self._tenant_delta_promql(metric, time_range)
        results = await self._client.query(promql)

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
    ) -> dict[str, dict[str, int]]:
        """(tenant, task) -> request count, from a sum-by(tenant,endpoint) query result."""
        tenant_task: dict[str, dict[str, int]] = {}
        for r in results:
            ep = r["metric"].get(PROMETHEUS_API_PATH_LABEL, "")
            tenant_label = r["metric"].get("tenant", "unknown")
            task = cls._resolve_task_key(ep)
            if task not in active_services:
                continue
            v = max(0, round(float(r["value"][1])))
            if v <= 0:
                continue
            bucket = tenant_task.setdefault(tenant_label, {})
            bucket[task] = bucket.get(task, 0) + v
        return tenant_task

    @staticmethod
    def _rank_tenants_by_total(
        tenant_task: dict[str, dict[str, int]]
    ) -> list[tuple[str, int, dict[str, int]]]:
        """(tenant, total, tasks) sorted by total descending."""
        return sorted(
            [(t, sum(tasks.values()), tasks) for t, tasks in tenant_task.items()],
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
    ) -> dict:
        """Heatmap matrix: top-N tenants × per-service request counts.

        Uses a single sum by(tenant, exported_endpoint) query with offset subtraction
        (same approach as service_breakdown) to avoid increase() extrapolation errors.
        When ``tenant`` is given, the matrix is scoped to that single tenant.
        """
        active_services = services or list(SERVICE_BREAKDOWN_CONFIG)

        _ep = f'{PROMETHEUS_API_PATH_LABEL}=~"{SERVICE_BREAKDOWN_ENDPOINT_REGEX}"'
        _tenant_sel = f',tenant="{escape_label_value(tenant)}"' if tenant else ''
        base_sel = '{' + _ep + ',tenant!="unknown"' + _tenant_sel + '}'
        metric = f"{_METRIC}{base_sel}"
        window = TIME_RANGES.get(time_range or "all")

        if window:
            promql = (
                f"sum by(tenant, {PROMETHEUS_API_PATH_LABEL}) ("
                f"({metric} unless {metric} offset {window})"
                f" or (increase({metric}[{window}]) > 0)"
                f") > 0"
            )
        else:
            promql = f"sum by(tenant, {PROMETHEUS_API_PATH_LABEL}) ({metric}) > 0"

        results = await self._client.query(promql)
        tenant_task = self._accumulate_tenant_task_counts(results, active_services)
        ranked = self._rank_tenants_by_total(tenant_task)
        grand_total = sum(r[1] for r in ranked)
        top = ranked[:limit]

        rows = [
            self._heatmap_row(idx + 1, tenant_label, total, tasks, active_services, grand_total)
            for idx, (tenant_label, total, tasks) in enumerate(top)
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
    ) -> tuple[list[str], list]:
        """Per-service native-unit scalar query coroutines — one per task
        that has a real Prometheus Histogram _sum metric (SERVICE_BREAKDOWN_CONFIG).

        service_filter (the frontend's enabled-task-type allowlist), when
        given, skips the native-unit query entirely for excluded tasks —
        a query-level reduction, not just a display-level one."""
        native_tasks: list[str] = []
        native_coros = []
        for task, cfg in SERVICE_BREAKDOWN_CONFIG.items():
            if service_filter is not None and task not in service_filter:
                continue
            native_metric = cfg.get("native_metric")
            if not native_metric:
                continue
            extra = cfg.get("native_extra_labels") or []
            parts = [f'tenant="{escape_label_value(tenant)}"'] if tenant else []
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

    @staticmethod
    def _service_breakdown_rows(
        totals: dict, successes: dict, natives: dict,
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
                "native_unit_suffix": cfg["native_unit_suffix"],
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
    def _label_dict(results: list, label: str) -> dict:
        """Map a label's value -> rounded sum from a `sum by(<label>)` result vector."""
        out: dict = {}
        for r in results:
            key = r["metric"].get(label, "")
            out[key] = out.get(key, 0) + round(float(r["value"][1]))
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
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return f"sum by(tenant) ({metric}) > 0"
        return (
            f"sum by(tenant) ("
            f"({metric} unless {metric} offset {window})"
            f" or (increase({metric}[{window}]) > 0)"
            f") > 0"
        )

    @staticmethod
    def _by_tenant_promql(metric: str, time_range: Optional[str], filter_zero: bool) -> str:
        window = TIME_RANGES.get(time_range or "all")
        if window:
            return (
                f"sum by(tenant) ("
                f"({metric} unless {metric} offset {window})"
                f" or (increase({metric}[{window}]) > 0)"
                f") > 0"
            )
        base = f"sum by(tenant) ({metric})"
        return f"{base} > 0" if filter_zero else base

    async def _fetch_valid_tenant_names(self) -> Optional[set]:
        """Return the set of currently-ACTIVE tenant organisation names from the auth DB.

        The Prometheus ``tenant`` label carries the organisation name (see
        ai4i_core.observability.middleware), so filtering against still-valid
        tenants must match on that same value. Restricted to status='ACTIVE'
        so PENDING/SUSPENDED/DEACTIVATED tenants — who can't currently
        authenticate (see APIKeyService.user_may_use_api_keys) but may still
        have in-window Prometheus series from before their status changed —
        don't inflate the Active Tenants count on the Usage Dashboard.
        Returns None when the auth DB is unavailable so callers fall back to
        unfiltered Prometheus results rather than returning an empty count.
        """
        if self._auth_db is None:
            return None
        try:
            rows = await self._auth_db.execute(
                text("SELECT organisation FROM tenants WHERE status = 'ACTIVE'")
            )
            return {r[0] for r in rows.all()}
        except Exception:
            logger.warning("_fetch_valid_tenant_names: auth DB query failed", exc_info=True)
            return None
