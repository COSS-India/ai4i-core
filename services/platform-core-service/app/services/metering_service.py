"""Metering business logic — PromQL construction, Prometheus calls, result shaping."""
import asyncio
import logging
from typing import Optional

from app.utils.prometheus_client import PrometheusClient
from app.utils.metering_promql_builder import (
    TIME_RANGES,
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

    # ── private helpers ─────────────────────────────────────────────────────

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
