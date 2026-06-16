"""Metering business logic — PromQL construction, Prometheus calls, result shaping."""
import asyncio
import logging
from typing import Optional

from app.utils.prometheus_client import PrometheusClient
from app.utils.metering_promql_builder import (
    TIME_RANGES,
    DOUBLE_TIME_RANGES,
    SERVICE_BREAKDOWN_CONFIG,
    SERVICE_BREAKDOWN_ENDPOINT_REGEX,
    ENDPOINT_TO_TASK,
    THROUGHPUT_BUCKET_CONFIG,
    apply_time_range,
    build_base_selectors,
    sum_over_window,
)

logger = logging.getLogger(__name__)

_METRIC = "telemetry_obsv_requests_total"


class MeteringService:
    def __init__(self, client: PrometheusClient) -> None:
        self._client = client

    # ── public methods ──────────────────────────────────────────────────────

    async def request_total(
        self,
        inference_only: bool,
        tenant: Optional[str],
        service_id: Optional[str],
        time_range: Optional[str],
    ) -> dict:
        label_str = build_base_selectors(inference_only, tenant, service_id)
        promql = f"sum({apply_time_range(f'{_METRIC}{label_str}', time_range)})"
        total = int(await self._client.scalar(promql))
        return {
            "total_requests": total,
            "filters": {
                "inference_only": inference_only,
                "tenant": tenant,
                "service_id": service_id,
                "time_range": time_range or "all",
            },
            "promql": promql,
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

    async def avg_requests_per_tenant(self, time_range: Optional[str]) -> dict:
        metric = f"{_METRIC}{build_base_selectors(inference_only=True)}"
        promql = f"avg(sum by(tenant) ({apply_time_range(metric, time_range)}))"
        avg = round(float(await self._client.scalar(promql)), 2)
        return {
            "avg_requests_per_tenant": avg,
            "filters": {"time_range": time_range or "all"},
            "promql": promql,
        }

    async def top_inference_services(
        self,
        limit: int,
        tenant: Optional[str],
        time_range: Optional[str],
    ) -> dict:
        metric = f"{_METRIC}{build_base_selectors(inference_only=True, tenant=tenant)}"
        promql = f"topk({limit}, sum by(endpoint) ({apply_time_range(metric, time_range)}))"
        results = await self._client.query(promql)

        services = [
            {
                "endpoint": r["metric"].get("endpoint", "unknown"),
                "total_requests": int(float(r["value"][1])),
            }
            for r in results
        ]
        grand_total = sum(s["total_requests"] for s in services)
        for s in services:
            s["percentage"] = round(s["total_requests"] / grand_total * 100, 1) if grand_total else 0.0

        return {
            "services": services,
            "grand_total": grand_total,
            "filters": {"tenant": tenant, "limit": limit, "time_range": time_range or "all"},
            "promql": promql,
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

    async def request_volume_health(
        self,
        inference_only: bool,
        tenant: Optional[str],
        service_id: Optional[str],
        time_range: Optional[str],
    ) -> dict:
        base = f"{_METRIC}{build_base_selectors(inference_only, tenant, service_id)}"
        success_selector = build_base_selectors(inference_only, tenant, service_id, extra=['status_code=~"2.."'])
        failed_selector = build_base_selectors(inference_only, tenant, service_id, extra=['status_code=~"[45].."'])
        success = f"{_METRIC}{success_selector}"
        failed = f"{_METRIC}{failed_selector}"

        total_q = sum_over_window(base, time_range)
        success_q = sum_over_window(success, time_range)
        failed_q = sum_over_window(failed, time_range)

        total_v, success_v, failed_v = await asyncio.gather(
            self._client.scalar(total_q),
            self._client.scalar(success_q),
            self._client.scalar(failed_q),
        )
        total_v, success_v, failed_v = round(total_v), round(success_v), round(failed_v)

        vs_previous_pct = None
        window = TIME_RANGES.get(time_range or "all")
        if window:
            prev_total = round(await self._client.scalar(
                f"sum(increase({base}[{window}] offset {window}))"
            ))
            if prev_total > 0:
                vs_previous_pct = round((total_v - prev_total) / prev_total * 100, 1)

        return {
            "total_requests": {"count": total_v, "vs_previous_pct": vs_previous_pct},
            "successful_requests": {
                "count": success_v,
                "success_rate_pct": round(success_v / total_v * 100, 2) if total_v else 0.0,
            },
            "failed_requests": {
                "count": failed_v,
                "failure_rate_pct": round(failed_v / total_v * 100, 2) if total_v else 0.0,
            },
            "filters": {
                "inference_only": inference_only,
                "tenant": tenant,
                "service_id": service_id,
                "time_range": time_range or "all",
            },
        }

    async def service_breakdown(self, tenant: Optional[str], time_range: Optional[str]) -> dict:
        """Per-service stats: requests, native units, success %, failed, vs prev period.

        Fires all Prometheus queries in a single asyncio.gather:
          - 4–5 endpoint-grouped queries for request counts / prev period
          - 1 scalar query per service that has a dedicated native-unit metric
        """
        # Use the broader regex so /api/v1/chat (LLM) is included alongside
        # the standard /api/v1/{task}/inference endpoints.
        _ep = f'endpoint=~"{SERVICE_BREAKDOWN_ENDPOINT_REGEX}",method="POST"'
        _tenant = f',tenant="{tenant}"' if tenant else ""
        base_sel    = "{" + _ep + _tenant + "}"
        success_sel = "{" + _ep + _tenant + ',status_code=~"2.."' + "}"
        failed_sel  = "{" + _ep + _tenant + ',status_code=~"[45].."' + "}"

        window = TIME_RANGES.get(time_range or "all")

        def _by_ep(selector: str) -> str:
            """Offset subtraction avoids increase() float extrapolation errors.

            increase() interpolates over scrape samples and returns a tiny float
            (e.g. 0.0012) for counters with very little history, which round()
            collapses to 0. Subtracting the offset snapshot gives exact integers.
            The inner `or` provides 0 for endpoints that didn't exist at offset.
            """
            metric = f"{_METRIC}{selector}"
            if not window:
                return f"sum by(endpoint) ({metric})"
            return (
                f"sum by(endpoint) ({metric})"
                f" - (sum by(endpoint) ({metric} offset {window})"
                f" or sum by(endpoint) ({metric} * 0))"
            )

        # ── Fixed-index queries (0-3, optional 4) ───────────────────────────
        fixed_queries = [
            self._client.query(_by_ep(base_sel)),     # 0 total
            self._client.query(_by_ep(success_sel)),  # 1 success
            self._client.query(_by_ep(failed_sel)),   # 2 failed
        ]
        # prev_period = requests during the window BEFORE the current window.
        # e.g. for 24h: counter@24h_ago - counter@48h_ago  (not the raw snapshot).
        double_window = DOUBLE_TIME_RANGES.get(time_range or "all") if window else None
        if window and double_window:
            prev_q = (
                f"(sum by(endpoint) ({_METRIC}{base_sel} offset {window})"
                f" or sum by(endpoint) ({_METRIC}{base_sel} * 0))"
                f" - (sum by(endpoint) ({_METRIC}{base_sel} offset {double_window})"
                f" or sum by(endpoint) ({_METRIC}{base_sel} * 0))"
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
            native_v = natives.get(task)
            prev_v = prevs.get(task)

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
        # Fall back to a 5-minute window when no explicit range is selected ("all").
        avg_q = f"sum(rate({metric}[{window}]))" if window else f"sum(rate({metric}[5m]))"
        avg_rps = round(float(await self._client.scalar(avg_q)), 4)

        # Peak RPS: fire one rate query per sub-bucket in parallel.
        # Bucket i=1 is the oldest (largest offset); i=count is the newest (offset 0).
        peak_rps: Optional[float] = None
        peak_label: Optional[str] = None

        bucket_cfg = THROUGHPUT_BUCKET_CONFIG.get(time_range or "")
        if bucket_cfg and window:
            count = bucket_cfg["count"]
            bw = bucket_cfg["bucket_window"]
            unit = bucket_cfg["offset_unit"]
            factor = bucket_cfg["offset_factor"]
            prefix = bucket_cfg["label_prefix"]

            def _bucket_query(i: int) -> str:
                offset_steps = count - i
                if offset_steps == 0:
                    return f"sum(rate({metric}[{bw}]))"
                return f"sum(rate({metric}[{bw}] offset {offset_steps * factor}{unit}))"

            rates = await asyncio.gather(
                *[self._client.scalar(_bucket_query(i)) for i in range(1, count + 1)],
                return_exceptions=True,
            )

            valid = [
                (i + 1, float(v))
                for i, v in enumerate(rates)
                if not isinstance(v, Exception)
            ]
            if valid:
                peak_i, peak_v = max(valid, key=lambda x: x[1])
                peak_rps = round(peak_v, 2)
                peak_label = f"{prefix}{peak_i}"

        return {
            "avg_rps": avg_rps,
            "peak_rps": peak_rps,
            "peak_label": peak_label,
            "filters": {
                "inference_only": inference_only,
                "tenant": tenant,
                "service_id": service_id,
                "time_range": time_range or "all",
            },
        }

    async def top_tenants_throughput(
        self,
        limit: int,
        inference_only: bool,
        time_range: Optional[str],
    ) -> dict:
        label_str = build_base_selectors(inference_only)
        metric = f"{_METRIC}{label_str}"
        window = TIME_RANGES.get(time_range or "all")

        # Avg RPS per tenant over the selected window (5m fallback when window=None).
        rate_window = window or "5m"
        avg_q = f"topk({limit}, sum by(tenant) (rate({metric}[{rate_window}])))"
        avg_results = await self._client.query(avg_q)

        avg_by_tenant = {
            r["metric"].get("tenant", "unknown"): round(float(r["value"][1]), 4)
            for r in avg_results
        }
        top_tenants = list(avg_by_tenant)

        # Peak RPS per tenant: one rate query per time bucket, pick per-tenant max.
        peak_by_tenant: dict[str, float] = {t: 0.0 for t in top_tenants}
        bucket_cfg = THROUGHPUT_BUCKET_CONFIG.get(time_range or "")
        if bucket_cfg and window:
            count = bucket_cfg["count"]
            bw = bucket_cfg["bucket_window"]
            unit = bucket_cfg["offset_unit"]
            factor = bucket_cfg["offset_factor"]

            def _bucket_q(i: int) -> str:
                offset_steps = count - i
                if offset_steps == 0:
                    return f"sum by(tenant) (rate({metric}[{bw}]))"
                return f"sum by(tenant) (rate({metric}[{bw}] offset {offset_steps * factor}{unit}))"

            bucket_results = await asyncio.gather(
                *[self._client.query(_bucket_q(i)) for i in range(1, count + 1)],
                return_exceptions=True,
            )
            for result in bucket_results:
                if isinstance(result, Exception):
                    continue
                for r in result:
                    tenant = r["metric"].get("tenant", "unknown")
                    if tenant in peak_by_tenant:
                        v = float(r["value"][1])
                        if v > peak_by_tenant[tenant]:
                            peak_by_tenant[tenant] = v

        tenants = sorted(
            [
                {
                    "tenant": t,
                    "avg_rps": avg_by_tenant[t],
                    "peak_rps": round(peak_by_tenant[t], 3) if peak_by_tenant.get(t) else None,
                }
                for t in top_tenants
            ],
            key=lambda x: x["avg_rps"],
            reverse=True,
        )

        return {
            "tenants": tenants,
            "filters": {
                "limit": limit,
                "inference_only": inference_only,
                "time_range": time_range or "all",
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
                task = parts[2] if len(parts) >= 4 else ep
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
        """Per-tenant request delta using offset subtraction instead of increase().

        increase() extrapolates: a series that is only 2h old in a 7d query returns
        2/168 of its real counter value. Offset subtraction gives the exact integer
        difference; series absent at the offset point contribute their full current value.
        """
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return f"sum by(tenant) ({metric}) > 0"
        return (
            f"sum by(tenant) ({metric})"
            f" - (sum by(tenant) ({metric} offset {window})"
            f" or sum by(tenant) ({metric} * 0))"
        )

    @staticmethod
    def _by_tenant_promql(metric: str, time_range: Optional[str], filter_zero: bool) -> str:
        """PromQL that sums per-tenant over a rolling window, including new series.

        The OR clause rescues series that first appeared mid-window — increase() would
        return 0 for them because Prometheus never saw the 0→N transition at the offset point.
        """
        window = TIME_RANGES.get(time_range or "all")
        if window:
            windowed = apply_time_range(metric, time_range)
            return (
                f"sum by(tenant) ({windowed}) > 0"
                f" or (sum by(tenant) ({metric}) unless (sum by(tenant) ({metric} offset {window}) > 0))"
            )
        base = f"sum by(tenant) ({metric})"
        return f"{base} > 0" if filter_zero else base
