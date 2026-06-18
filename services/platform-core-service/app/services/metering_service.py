"""Metering business logic — PromQL construction, Prometheus calls, result shaping."""
import asyncio
import logging
import time as _time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.prometheus_client import PrometheusClient
from app.utils.metering_promql_builder import (
    TIME_RANGES,
    DOUBLE_TIME_RANGES,
    SERVICE_BREAKDOWN_CONFIG,
    SERVICE_BREAKDOWN_ENDPOINT_REGEX,
    ENDPOINT_TO_TASK,
    WINDOW_STEP,
    build_base_selectors,
    sum_over_window,
)

_WINDOW_SECONDS: dict = {
    "1h":  3_600,
    "24h": 86_400,
    "7d":  604_800,
    "30d": 2_592_000,
}

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

        total_vs_prev: Optional[float] = None
        success_rate_vs_prev: Optional[float] = None
        avg_rps_vs_prev: Optional[float] = None

        if window:
            prev_total = max(0, round(_float(raw[3])))
            prev_success = max(0, round(_float(raw[4])))
            prev_avg_rps = _float(raw[5])

            if prev_total > 0:
                total_vs_prev = round((total_v - prev_total) / prev_total * 100, 1)
                prev_success_rate = round(prev_success / prev_total * 100, 2)
                # pp change so that "97.35 → 97.45" reports as +0.1
                success_rate_vs_prev = round(success_rate - prev_success_rate, 2)

            if prev_avg_rps > 0:
                avg_rps_vs_prev = round((avg_rps_v - prev_avg_rps) / prev_avg_rps * 100, 1)

        return {
            "total_requests": {
                "count": total_v,
                "formatted": self._format_count(total_v),
                "vs_previous_pct": total_vs_prev,
            },
            "success_rate": {
                "rate_pct": success_rate,
                "vs_previous_pct": success_rate_vs_prev,
            },
            "avg_rps": {
                "value": avg_rps_v,
                "vs_previous_pct": avg_rps_vs_prev,
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
        results = await self._client.query(promql)
        tenants = [
            {
                "tenant": r["metric"].get("tenant", "unknown"),
                "request_count": int(float(r["value"][1])),
            }
            for r in results
        ]
        return {
            "active_tenants": tenants,
            "count": len(tenants),
            "filters": {"time_range": time_range or "all"},
            "promql": promql,
        }

    async def tenant_count(self) -> dict:
        if self._auth_db is None:
            return {
                "total_tenants": None,
                "new_tenants": None,
                "auth_db_available": False,
            }
        total, new_tenants = await asyncio.gather(
            self._auth_db.execute(text("SELECT COUNT(*) FROM tenants")),
            self._auth_db.execute(
                text("SELECT COUNT(*) FROM tenants WHERE created_at >= NOW() - INTERVAL '7 days'")
            ),
        )
        return {
            "total_tenants": total.scalar(),
            "new_tenants": new_tenants.scalar(),
            "auth_db_available": True,
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
        failed_sel  = "{" + _base + ',status_code=~"[45].."' + "}"

        window = TIME_RANGES.get(time_range or "all")

        def _by_ep(selector: str) -> str:
            metric = f"{_METRIC}{selector}"
            if not window:
                return f"sum by(endpoint) ({metric})"
            return (
                f"sum by(endpoint) ("
                f"(increase({metric}[{window}]) > 0)"
                f" or ({metric} unless {metric} offset {window})"
                f")"
            )

        # ── Fixed-index queries (0-3, optional 4) ───────────────────────────
        fixed_queries = [
            self._client.query(_by_ep(base_sel)),     # 0 total
            self._client.query(_by_ep(success_sel)),  # 1 success
            self._client.query(_by_ep(failed_sel)),   # 2 failed
        ]
        # prev_period = requests during the window BEFORE the current window.
        double_window = DOUBLE_TIME_RANGES.get(time_range or "all") if window else None
        if window and double_window:
            prev_q = (
                f"sum by(endpoint) (increase({_METRIC}{base_sel} offset {window}[{window}]))"
            )
            fixed_queries.append(self._client.query(prev_q))  # 3 prev (optional)

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
            if window:
                q = (
                    f"(sum({native_metric}{sel}) or vector(0))"
                    f" - (sum({native_metric}{sel} offset {window}) or vector(0))"
                )
            else:
                q = f"sum({native_metric}{sel})"
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
        faileds = self._endpoint_dict(_safe_list(raw[2]))
        prevs = self._endpoint_dict(_safe_list(raw[3])) if (window and double_window) else {}

        # Unpack native results (start after fixed queries).
        # Only store when > 0: a 0.0 result means the metric doesn't exist yet
        # (the or vector(0) fallback fires), so we return null rather than 0.
        native_offset = len(fixed_queries)
        natives: dict = {}
        for i, task in enumerate(native_tasks):
            v = _safe_float(raw[native_offset + i])
            if v is not None and v > 0:
                natives[task] = round(v)

        # ── Assemble service rows ────────────────────────────────────────────
        services = []
        for task, cfg in SERVICE_BREAKDOWN_CONFIG.items():
            total_v = totals.get(task, 0)
            success_v = successes.get(task, 0)
            failed_v = faileds.get(task, 0)
            prev_v = prevs.get(task)

            if cfg.get("use_success_as_native"):
                native_v = success_v or None
            else:
                raw_native = natives.get(task)
                if raw_native is not None and cfg.get("divide_by_60"):
                    native_v = round(raw_native / 60, 2)
                else:
                    native_v = raw_native

            vs_prev_pct = None
            if prev_v is not None and prev_v > 0:
                vs_prev_pct = round((total_v - prev_v) / prev_v * 100, 1)

            services.append({
                "service": cfg["display_name"],
                "metering_unit": cfg["metering_unit"],
                "requests": total_v,
                "native_units": native_v,
                "native_unit_suffix": cfg["native_unit_suffix"],
                "success_pct": round(success_v / total_v * 100, 2) if total_v else 0.0,
                "failed": failed_v,
                "vs_prev_period_pct": vs_prev_pct,
                "prev_requests": prev_v,
            })

        services.sort(key=lambda s: s["requests"], reverse=True)

        return {
            "services": services,
            "filters": {"tenant": tenant, "time_range": time_range or "all"},
        }

    async def tenant_ranking(self, limit: int, time_range: Optional[str]) -> dict:
        metric = f"{_METRIC}{build_base_selectors(inference_only=True)}"
        # Offset subtraction avoids increase() extrapolation errors on short-lived series.
        # increase() scales down the raw counter by (observed_duration / window_duration),
        # so a series that's only a few hours old in a 7d query returns ~0 instead of its
        # real counter value. Subtracting the offset snapshot gives exact integer deltas and
        # correctly handles series that didn't exist at the start of the window (implied 0).
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
            "total_tenant_count": len(all_tenants),
            "filters": {"limit": limit, "time_range": time_range or "all"},
        }

    async def throughput(
        self,
        inference_only: bool,
        tenant: Optional[str],
        service_id: Optional[str],
        time_range: Optional[str],
    ) -> dict:
        label_str = build_base_selectors(inference_only, tenant, service_id)
        metric = f"{_METRIC}{label_str}"
        window = TIME_RANGES.get(time_range or "all")

        # Avg RPS: rate() already returns per-second rate averaged over the window.
        avg_q = f"sum(rate({metric}[{window}]))" if window else f"sum(rate({metric}[5m]))"
        avg_rps = round(await self._client.scalar(avg_q), 4)

        # Peak RPS: one range query over the window, find the max point.
        peak_rps: Optional[float] = None
        peak_at: Optional[str] = None

        if window and time_range in WINDOW_STEP:
            now = _time.time()
            w_secs = _WINDOW_SECONDS[time_range]
            step = WINDOW_STEP[time_range]
            range_results = await self._client.query_range(
                f"sum(rate({metric}[1m]))",
                start=now - w_secs,
                end=now,
                step=step,
            )
            if range_results:
                points = range_results[0].get("values", [])
                if points:
                    ts, val = max(points, key=lambda p: float(p[1]))
                    peak_rps = round(float(val), 4)
                    peak_at = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "avg_rps": avg_rps,
            "peak_rps": peak_rps,
            "peak_at": peak_at,
            "filters": {
                "inference_only": inference_only,
                "tenant": tenant,
                "service_id": service_id,
                "time_range": time_range or "all",
            },
        }

    async def usage_by_tenant_service(
        self,
        limit: int,
        time_range: Optional[str],
        services: Optional[list[str]],
    ) -> dict:
        """Heatmap matrix: top-N tenants × per-service request counts.

        Uses a single sum by(tenant, endpoint) query with offset subtraction
        (same approach as service_breakdown) to avoid increase() extrapolation errors.
        """
        active_services = services or list(SERVICE_BREAKDOWN_CONFIG)

        _ep = f'endpoint=~"{SERVICE_BREAKDOWN_ENDPOINT_REGEX}"'
        base_sel = '{' + _ep + ',tenant!="unknown"}'
        metric = f"{_METRIC}{base_sel}"
        window = TIME_RANGES.get(time_range or "all")

        if window:
            promql = (
                f"sum by(tenant, endpoint) ("
                f"(increase({metric}[{window}]) > 0)"
                f" or ({metric} unless {metric} offset {window})"
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
                    }
                    for svc in active_services
                },
                "total": total,
                "formatted_total": self._format_count(total),
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
            f"(increase({metric}[{window}]) > 0)"
            f" or ({metric} unless {metric} offset {window})"
            f") > 0"
        )

    @staticmethod
    def _by_tenant_promql(metric: str, time_range: Optional[str], filter_zero: bool) -> str:
        window = TIME_RANGES.get(time_range or "all")
        if window:
            return (
                f"sum by(tenant) ("
                f"(increase({metric}[{window}]) > 0)"
                f" or ({metric} unless {metric} offset {window})"
                f") > 0"
            )
        base = f"sum by(tenant) ({metric})"
        return f"{base} > 0" if filter_zero else base
