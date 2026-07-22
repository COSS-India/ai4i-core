"""Metering business logic — PromQL construction, Prometheus calls, result shaping."""
import asyncio
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.prometheus_client import PrometheusClient
from app.utils.metering_promql_builder import (
    TIME_RANGES,
    SERVICE_BREAKDOWN_CONFIG,
    SERVICE_BREAKDOWN_ENDPOINT_REGEX,
    ENDPOINT_TO_TASK,
    build_base_selectors,
    sum_over_window,
)

logger = logging.getLogger(__name__)

_METRIC = "telemetry_obsv_requests_total"


class MeteringService:
    def __init__(self, client: PrometheusClient, auth_db: Optional[AsyncSession] = None) -> None:
        self._client = client
        self._auth_db = auth_db

    # ── public methods ──────────────────────────────────────────────────────

    async def request_total(
        self,
        inference_only: bool,
        tenant: Optional[str],
        service_id: Optional[str],
        time_range: Optional[str],
    ) -> dict:
        label_str = build_base_selectors(inference_only, tenant, service_id)
        success_label_str = build_base_selectors(
            inference_only, tenant, service_id, extra=['status_code=~"2.."']
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
        avg_rps_v = round(_float(raw[2]), 2)
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
            prev_avg_rps_v = round(prev_avg_rps, 2)
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
        metric = f"{_METRIC}{build_base_selectors(inference_only=True)}"
        promql = self._by_tenant_promql(metric, time_range, filter_zero=True)
        prom_results, valid_ids = await asyncio.gather(
            self._client.query(promql),
            self._fetch_valid_tenant_ids(),
        )
        # Filter Prometheus results to only tenants that currently exist in the
        # DB. Without this, deleted tenants whose Prometheus series are still
        # within the retention window inflate 7d/30d counts after a DB flush.
        tenants = [
            {
                "tenant": r["metric"].get("tenant", "unknown"),
                "request_count": int(float(r["value"][1])),
            }
            for r in prom_results
            if valid_ids is None or r["metric"].get("tenant") in valid_ids
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

    async def usage_concentration(self, limit: int, time_range: Optional[str]) -> dict:
        metric = f"{_METRIC}{build_base_selectors(inference_only=True)}"
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

    async def service_breakdown(self, tenant: Optional[str], time_range: Optional[str]) -> dict:
        """Per-service stats: requests, native units, success %, failed, vs prev period.

        Fires all Prometheus queries in a single asyncio.gather:
          - 4–5 endpoint-grouped queries for request counts / prev period
          - 1 scalar query per service that has a dedicated native-unit metric
        """
        # Use the broader regex so /api/v1/chat (LLM) is included alongside
        # the standard /api/v1/{task}/inference endpoints.
        _ep = f'endpoint=~"{SERVICE_BREAKDOWN_ENDPOINT_REGEX}"'
        _base = _ep + ',tenant!="unknown"' + (f',tenant="{tenant}"' if tenant else "")
        base_sel    = "{" + _base + "}"
        success_sel = "{" + _base + ',status_code=~"2.."' + "}"

        window = TIME_RANGES.get(time_range or "all")

        def _by_ep(selector: str) -> str:
            metric = f"{_METRIC}{selector}"
            if not window:
                return f"sum by(endpoint) ({metric})"
            return (
                f"sum by(endpoint) ("
                f"({metric} unless {metric} offset {window})"
                f" or (increase({metric}[{window}]) > 0)"
                f")"
            )

        # ── Fixed-index queries ──────────────────────────────────────────────
        fixed_queries = [
            self._client.query(_by_ep(base_sel)),     # 0 total
            self._client.query(_by_ep(success_sel)),  # 1 success
        ]

        # ── Per-service native-unit scalar queries ───────────────────────────
        # Only for tasks that have a real Prometheus Histogram _sum metric.
        native_tasks: list[str] = []
        native_coros = []
        for task, cfg in SERVICE_BREAKDOWN_CONFIG.items():
            native_metric = cfg.get("native_metric")
            if not native_metric:
                continue
            extra = cfg.get("native_extra_labels") or []
            parts = [f'tenant="{tenant}"'] if tenant else []
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

        raw = await asyncio.gather(*fixed_queries, *native_coros, return_exceptions=True)

        def _safe_list(r):
            return r if not isinstance(r, Exception) else []

        def _safe_float(r):
            return r if not isinstance(r, Exception) else None

        # Unpack fixed results
        totals = self._endpoint_dict(_safe_list(raw[0]))
        successes = self._endpoint_dict(_safe_list(raw[1]))

        # Unpack native results (start after fixed queries). A 0.0 result means
        # either no usage occurred or the metric doesn't exist yet (the
        # `or vector(0)` fallback fires) — both cases legitimately report 0.
        native_offset = len(fixed_queries)
        natives: dict = {}
        for i, task in enumerate(native_tasks):
            v = _safe_float(raw[native_offset + i])
            if v is not None:
                natives[task] = round(v)

        # ── Assemble service rows ────────────────────────────────────────────
        services = []
        for task, cfg in SERVICE_BREAKDOWN_CONFIG.items():
            total_v = totals.get(task, 0)
            success_v = successes.get(task, 0)

            raw_native = natives.get(task, 0)
            if cfg.get("divide_by_60"):
                native_v = round(raw_native / 60, 2)
            else:
                native_v = raw_native

            services.append({
                "service": cfg["display_name"],
                "requests": total_v,
                "native_units": native_v,
                "native_unit_suffix": cfg["native_unit_suffix"],
                "success_pct": round(success_v / total_v * 100, 2) if total_v else 0.0,
            })

        services.sort(key=lambda s: s["requests"], reverse=True)

        return {
            "services": services,
            "filters": {"tenant": tenant, "time_range": time_range or "all"},
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

    async def usage_by_tenant_service(
        self,
        limit: int,
        time_range: Optional[str],
        services: Optional[list[str]],
        tenant: Optional[str] = None,
    ) -> dict:
        """Heatmap matrix: top-N tenants × per-service request counts.

        Uses a single sum by(tenant, endpoint) query with offset subtraction
        (same approach as service_breakdown) to avoid increase() extrapolation errors.
        When ``tenant`` is given, the matrix is scoped to that single tenant.
        """
        active_services = services or list(SERVICE_BREAKDOWN_CONFIG)

        _ep = f'endpoint=~"{SERVICE_BREAKDOWN_ENDPOINT_REGEX}"'
        _tenant_sel = f',tenant="{tenant}"' if tenant else ''
        base_sel = '{' + _ep + ',tenant!="unknown"' + _tenant_sel + '}'
        metric = f"{_METRIC}{base_sel}"
        window = TIME_RANGES.get(time_range or "all")

        if window:
            promql = (
                f"sum by(tenant, endpoint) ("
                f"({metric} unless {metric} offset {window})"
                f" or (increase({metric}[{window}]) > 0)"
                f") > 0"
            )
        else:
            promql = f"sum by(tenant, endpoint) ({metric}) > 0"

        results = await self._client.query(promql)

        # Accumulate (tenant, task) → count
        tenant_task: dict[str, dict[str, int]] = {}
        for r in results:
            ep = r["metric"].get("endpoint", "")
            tenant_label = r["metric"].get("tenant", "unknown")
            task = ENDPOINT_TO_TASK.get(ep)
            if task is None:
                parts = [p for p in ep.split("/") if p]
                raw = parts[2] if len(parts) >= 4 else None
                task = raw.replace("-", "_") if raw else None
            if task not in active_services:
                continue
            v = max(0, round(float(r["value"][1])))
            if v <= 0:
                continue
            bucket = tenant_task.setdefault(tenant_label, {})
            bucket[task] = bucket.get(task, 0) + v

        # Sort tenants by total descending, pick top N
        ranked = sorted(
            [(t, sum(tasks.values()), tasks) for t, tasks in tenant_task.items()],
            key=lambda x: x[1],
            reverse=True,
        )
        grand_total = sum(r[1] for r in ranked)
        top = ranked[:limit]

        rows = [
            {
                "rank": idx + 1,
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
    def _endpoint_dict(results: list) -> dict:
        """Map task key → rounded value from a `sum by(endpoint)` result vector.

        Handles two endpoint patterns:
          - Standard: /api/v1/{task}/inference  → task = path segment at index 2
          - Non-standard: looked up via ENDPOINT_TO_TASK (e.g. /api/v1/chat → llm)
        """
        out: dict = {}
        for r in results:
            ep = r["metric"].get("endpoint", "")
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

    async def _fetch_valid_tenant_ids(self) -> Optional[set]:
        """Return the set of currently-valid tenant ID strings from the auth DB.

        Returns None when the auth DB is unavailable so callers fall back to
        unfiltered Prometheus results rather than returning an empty count.
        """
        if self._auth_db is None:
            return None
        try:
            rows = await self._auth_db.execute(text("SELECT id FROM tenants"))
            return {str(r[0]) for r in rows.all()}
        except Exception:
            logger.warning("_fetch_valid_tenant_ids: auth DB query failed", exc_info=True)
            return None
