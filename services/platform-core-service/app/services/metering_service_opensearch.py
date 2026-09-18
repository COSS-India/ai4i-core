"""OpenSearch-backed MeteringService — exact request counts from RequestMiddleware's
per-request log line (`logs-*`), replacing PromQL's increase()/rate() estimates
for the KPIs that only need a count of real events (arch-docs/3055-metering-
opensearch-request-counts.md, §7).

Subclasses MeteringService rather than reimplementing it: every helper that
doesn't touch Prometheus directly — `_format_count`, `_merge_tenant_rows`,
`_resolve_task_key`, `_accumulate_tenant_task_counts`, `_rank_tenants_by_total`,
`_heatmap_row`, `_fetch_valid_tenant_ids`, `_resolve_tenant_names`,
`tenant_count`, `registry_model_count`, `model_consumption_ranking`,
`model_consumption_kpis` — is inherited completely unchanged and reused as-is
(doc §7: "only the row shape being fed in changes, not the aggregation logic
itself"). Several OpenSearch aggregation results are deliberately reshaped
into the same `{"metric": {...}, "value": [_, count]}` row shape Prometheus's
own query results use, specifically so those inherited helpers can consume
them without modification.

Currently overridden — every request-count KPI across all four tabs
(Overview, Tenant Consumption, Service Consumption, Model Consumption):
  request_total, request_volume_chart, active_tenants,
  active_tenants_count_previous, avg_per_active_tenant_previous,
  usage_concentration, tenant_ranking, usage_by_tenant_service,
  model_usage_growth_pct, service_breakdown, model_breakdown.
service_breakdown/model_breakdown are genuine hybrids, not full OpenSearch
swaps: their native-unit values (characters/tokens/audio-minutes) still come
from the inherited Prometheus-backed `_native_unit_queries`/
`_model_native_unit_queries`, since those metrics stay on Prometheus
permanently (doc §9). model_breakdown also reuses
`MeteringService._shape_model_breakdown` — the ghost-filtering/per-service/
per-model rollup logic, extracted verbatim from the Prometheus version
specifically so this override doesn't duplicate its several ROLLOUT-NOTE-
documented subtleties; only the composite-aggregation row-fetching differs
(§7.9).

Passing a real PrometheusClient into `__init__` is still required — not just
for native units, but because `tenant_count`, `registry_model_count`,
`model_consumption_ranking`, and `model_consumption_kpis` (inherited,
pure-Postgres/pure-Python, unchanged) and the native-unit queries above all
still run through it.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from app.schemas.metering import Graph, GraphPoint, GraphSeries
from app.services.metering_service import (
    MeteringService,
    _UNSET,
    _Unset,
    _WINDOW_SECONDS,
    _step_seconds,
)
from app.services.pay_per_use import inference_type_cache
from app.utils.metering_promql_builder import (
    API_KEY_AUTH_TYPE,
    ENDPOINT_TO_TASK,
    PROMETHEUS_API_PATH_LABEL,
    SERVICE_BREAKDOWN_CONFIG,
    TIME_RANGES,
    WINDOW_STEP,
)
from app.utils.opensearch_log_client import (
    OpenSearchLogClient,
    STATUS_FAILED_RANGE,
    STATUS_SUCCESS_RANGE,
)

logger = logging.getLogger(__name__)

# LLM chat paths — mirrors LLM_CHAT_ENDPOINT_REGEX (metering_promql_builder.py),
# used by model_usage_growth_pct, which is LLM-only.
_LLM_CHAT_PATHS = ["/api/v1/chat", "/api/v1/chat/completions"]


def _task_type_paths(task_types: list[str]) -> list[str]:
    """Literal `path` values for a list of metering task-type keys — the
    OpenSearch equivalent of build_task_type_selector's PromQL regex
    alternation, as an exact-match `terms` list instead of a regex."""
    paths: list[str] = []
    for task in task_types:
        literal = [ep for ep, t in ENDPOINT_TO_TASK.items() if t == task]
        if literal:
            paths.extend(literal)
        else:
            paths.append(f"/api/v1/{task.replace('_', '-')}/inference")
    return paths


class OpenSearchMeteringService(MeteringService):
    def __init__(
        self,
        os_client: OpenSearchLogClient,
        client=None,
        auth_db=None,
        service_repo=None,
        model_repo=None,
    ) -> None:
        super().__init__(client, auth_db, service_repo, model_repo)
        self._os_client = os_client

    # ── shared query-building helpers ───────────────────────────────────

    @staticmethod
    def _double_window(window: str) -> str:
        """"24h" -> "48h", "7d" -> "14d" — doubling a TIME_RANGES duration
        string for the vs-previous-period outer range (doc §7.5)."""
        m = re.fullmatch(r"(\d+)([a-z]+)", window)
        return f"{int(m.group(1)) * 2}{m.group(2)}" if m else window

    @staticmethod
    def _status_filters_agg() -> dict:
        return {
            "filters": {
                "filters": {
                    "success": {"range": {"statusCode": dict(STATUS_SUCCESS_RANGE)}},
                    "failed": {"range": {"statusCode": dict(STATUS_FAILED_RANGE)}},
                }
            }
        }

    @staticmethod
    def _base_filters(
        *,
        tenant_id: Optional[str] = None,
        service_id: Optional[str] = None,
        auth_type: Optional[str] = None,
        task_types: Optional[list[str]] = None,
        inference_only: bool = True,
    ) -> list[dict]:
        """OpenSearch `bool.filter` clauses matching build_base_selectors'
        PromQL selector, minus the `tenant!="unknown"` guard (OpenSearch
        never logs a placeholder tenant — RequestMiddleware simply omits
        tenant_id when it isn't present, see ai4i_core middleware.py) and
        minus `tenant` (the organisation name) — only `tenant_id` is ever
        logged (doc §7.2), so a caller that only has the name has nothing to
        filter on for OpenSearch; the name is resolved for DISPLAY via
        `_resolve_tenant_names` after the query, same as the Prometheus path
        already does.
        """
        filters: list[dict] = []
        if tenant_id:
            filters.append({"term": {"tenant_id": tenant_id}})
        if service_id:
            filters.append({"term": {"service_id": service_id}})
        if auth_type:
            # Fail-open: match auth_type OR the field being absent entirely —
            # mirrors api_key_auth_type_selector's `auth_type=~"api_key|"`.
            filters.append({
                "bool": {
                    "should": [
                        {"term": {"auth_type": auth_type}},
                        {"bool": {"must_not": {"exists": {"field": "auth_type"}}}},
                    ],
                    "minimum_should_match": 1,
                }
            })
        if inference_only:
            paths = _task_type_paths(task_types) if task_types else None
            if paths:
                filters.append({"terms": {"path": paths}})
            else:
                # INFERENCE_ENDPOINT_REGEX equivalent: any path ending in
                # "/inference", plus the two LLM chat paths.
                filters.append({
                    "bool": {
                        "should": [
                            {"wildcard": {"path": "*/inference"}},
                            {"terms": {"path": _LLM_CHAT_PATHS}},
                        ],
                        "minimum_should_match": 1,
                    }
                })
        return filters

    @staticmethod
    def _windowed_query(window: Optional[str], filters: list[dict]) -> dict:
        if window:
            return {"bool": {"filter": [
                {"range": {"@timestamp": {"gte": f"now-{window}", "lte": "now"}}},
                *filters,
            ]}}
        return {"bool": {"filter": filters}} if filters else {"match_all": {}}

    # ── overridden public methods ───────────────────────────────────────

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
        window = TIME_RANGES.get(time_range or "all")
        base_filters = self._base_filters(
            tenant_id=tenant_id, service_id=service_id, auth_type=auth_type,
            task_types=task_types, inference_only=inference_only,
        )

        total_vs_prev = success_rate_vs_prev = avg_rps_vs_prev = None
        failed_vs_prev = successful_vs_prev = None
        prev_total_v = prev_failed_v = prev_success_v = None
        prev_success_rate_v = prev_avg_rps_v = None

        if window:
            double_window = self._double_window(window)
            query = {"bool": {"filter": [
                {"range": {"@timestamp": {"gte": f"now-{double_window}", "lte": "now"}}},
                *base_filters,
            ]}}
            aggs = {
                "by_period": {
                    "filters": {"filters": {
                        "current": {"range": {"@timestamp": {"gte": f"now-{window}", "lt": "now"}}},
                        "previous": {"range": {"@timestamp": {
                            "gte": f"now-{double_window}", "lt": f"now-{window}",
                        }}},
                    }},
                    "aggs": {"by_status": self._status_filters_agg()},
                }
            }
            aggregations = await self._os_client.aggregate(query, aggs)
            periods = aggregations.get("by_period", {}).get("buckets", {})
            cur = periods.get("current", {})
            prev = periods.get("previous", {})

            def _period_counts(bucket: dict) -> tuple[int, int, int]:
                total = int(bucket.get("doc_count", 0))
                status = bucket.get("by_status", {}).get("buckets", {})
                success = int(status.get("success", {}).get("doc_count", 0))
                failed = int(status.get("failed", {}).get("doc_count", 0))
                return total, success, failed

            total_v, success_v, failed_v = _period_counts(cur)
            prev_total, prev_success, prev_failed = _period_counts(prev)

            success_rate = round(success_v / total_v * 100, 2) if total_v else 0.0
            avg_rps_v = round(total_v / _WINDOW_SECONDS[window], 4)
            prev_avg_rps = prev_total / _WINDOW_SECONDS[window]

            prev_total_v, prev_failed_v, prev_success_v = prev_total, prev_failed, prev_success
            prev_avg_rps_v = round(prev_avg_rps, 4)
            prev_success_rate_v = (
                round(prev_success / prev_total * 100, 2) if prev_total > 0 else 0.0
            )

            if prev_total > 0:
                total_vs_prev = round((total_v - prev_total) / prev_total * 100, 1)
                success_rate_vs_prev = round(success_rate - prev_success_rate_v, 2)
            if prev_failed > 0:
                failed_vs_prev = round((failed_v - prev_failed) / prev_failed * 100, 1)
            if prev_success > 0:
                successful_vs_prev = round((success_v - prev_success) / prev_success * 100, 1)
            if prev_avg_rps > 0:
                avg_rps_vs_prev = round((avg_rps_v - prev_avg_rps) / prev_avg_rps * 100, 1)
        else:
            # No window ("all"): total/success/failed are all-time counts,
            # but avg_rps still reflects a trailing 5-minute rate — mirrors
            # request_total's own `rate_window = window or "5m"` fallback
            # (a window=None avg_rps is "current throughput", not an
            # all-history average).
            query = {"bool": {"filter": base_filters}} if base_filters else {"match_all": {}}
            five_min_query = {"bool": {"filter": [
                {"range": {"@timestamp": {"gte": "now-5m", "lte": "now"}}}, *base_filters,
            ]}}
            total_v, five_min_total, aggregations = await asyncio.gather(
                self._os_client.count(query),
                self._os_client.count(five_min_query),
                self._os_client.aggregate(query, {"by_status": self._status_filters_agg()}),
            )
            status = aggregations.get("by_status", {}).get("buckets", {})
            success_v = int(status.get("success", {}).get("doc_count", 0))
            failed_v = int(status.get("failed", {}).get("doc_count", 0))
            success_rate = round(success_v / total_v * 100, 2) if total_v else 0.0
            avg_rps_v = round(five_min_total / 300, 4)

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

    async def request_volume_chart(
        self,
        window: str,
        tenant: Optional[str],
        task_types: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
        auth_type: Optional[str] = None,
    ) -> Optional[Graph]:
        if window not in WINDOW_STEP:
            return None

        step = WINDOW_STEP[window]
        # Same bucket-count alignment MeteringService.request_volume_chart()
        # (the Prometheus version) uses: when the window doesn't divide
        # evenly by the bucket width — only 30d/7d today, ceil(30/7)=5
        # buckets = 35 days — both backends must query the SAME total span
        # and bucket count, not the literal window, or a dual-run comparison
        # on that window disagrees permanently even with zero real drift
        # (caught in PR review — the literal-window query here undercounted
        # by up to one bucket width relative to Prometheus's aligned span).
        step_secs = _step_seconds(step)
        w_secs = _WINDOW_SECONDS[window]
        n_buckets = max(1, -(-w_secs // step_secs)) if step_secs else 1
        range_secs = n_buckets * step_secs

        base_filters = self._base_filters(
            tenant_id=tenant_id, auth_type=auth_type, task_types=task_types, inference_only=True,
        )
        query = {"bool": {"filter": [
            {"range": {"@timestamp": {"gte": f"now-{range_secs}s", "lte": "now"}}}, *base_filters,
        ]}}
        aggs = {
            "over_time": {
                "date_histogram": {
                    "field": "@timestamp",
                    "fixed_interval": step,
                    "extended_bounds": {"min": f"now-{range_secs}s", "max": "now"},
                },
                "aggs": {"by_status": self._status_filters_agg()},
            }
        }
        aggregations = await self._os_client.aggregate(query, aggs)
        buckets = aggregations.get("over_time", {}).get("buckets", [])

        succ_points: list[GraphPoint] = []
        fail_points: list[GraphPoint] = []
        for b in buckets:
            ts_s = int(b["key"]) // 1000
            status = b.get("by_status", {}).get("buckets", {})
            succ_points.append(GraphPoint(ts=ts_s, value=int(status.get("success", {}).get("doc_count", 0))))
            fail_points.append(GraphPoint(ts=ts_s, value=int(status.get("failed", {}).get("doc_count", 0))))

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

    async def active_tenants(
        self, time_range: Optional[str], valid_names: Union[set, None, _Unset] = _UNSET
    ) -> dict:
        window = TIME_RANGES.get(time_range or "all")
        base_filters = self._base_filters(auth_type=API_KEY_AUTH_TYPE, inference_only=True)
        query = self._windowed_query(window, base_filters)
        aggs = {"tenants": {"terms": {"field": "tenant_id", "size": 10000}}}

        resolve_names = valid_names is _UNSET
        if valid_names is _UNSET:
            aggregations, valid_names = await asyncio.gather(
                self._os_client.aggregate(query, aggs),
                self._fetch_valid_tenant_ids(),
            )
        else:
            aggregations = await self._os_client.aggregate(query, aggs)

        buckets = aggregations.get("tenants", {}).get("buckets", [])
        # Every OpenSearch bucket already carries a real tenant_id (a `terms`
        # source excludes documents missing the field) — unlike Prometheus,
        # there's no pre-cutover "keep it anyway" case to special-case here
        # (doc §7.2: "no cutover-gap equivalent... every log line carries
        # tenant_id consistently from day one").
        rows = [
            {"metric": {"tenant_id": b["key"], "tenant": ""}, "value": [0, b["doc_count"]]}
            for b in buckets
            if valid_names is None or b["key"] in valid_names
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
        }

    async def active_tenants_count_previous(self, time_range: Optional[str]) -> Optional[int]:
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return None
        base_filters = self._base_filters(auth_type=API_KEY_AUTH_TYPE, inference_only=True)
        double_window = self._double_window(window)
        query = {"bool": {"filter": [
            {"range": {"@timestamp": {"gte": f"now-{double_window}", "lt": f"now-{window}"}}},
            *base_filters,
        ]}}
        try:
            aggregations = await self._os_client.aggregate(
                query, {"tenants": {"terms": {"field": "tenant_id", "size": 10000}}}
            )
            return len(aggregations.get("tenants", {}).get("buckets", []))
        except Exception:
            logger.warning("active_tenants_count_previous: OpenSearch query failed", exc_info=True)
            return None

    async def avg_per_active_tenant_previous(
        self, time_range: Optional[str], tenant: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[int]:
        window = TIME_RANGES.get(time_range or "all")
        if not window:
            return None
        base_filters = self._base_filters(
            tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE, inference_only=True,
        )
        double_window = self._double_window(window)
        query = {"bool": {"filter": [
            {"range": {"@timestamp": {"gte": f"now-{double_window}", "lt": f"now-{window}"}}},
            *base_filters,
        ]}}
        try:
            aggregations = await self._os_client.aggregate(
                query, {"tenants": {"terms": {"field": "tenant_id", "size": 10000}}}
            )
            buckets = aggregations.get("tenants", {}).get("buckets", [])
            active_v = len(buckets)
            total_v = sum(b["doc_count"] for b in buckets)
            return round(total_v / active_v) if active_v > 0 else None
        except Exception:
            logger.warning("avg_per_active_tenant_previous: OpenSearch query failed", exc_info=True)
            return None

    async def usage_concentration(
        self, limit: int, time_range: Optional[str], task_types: Optional[list[str]] = None,
    ) -> dict:
        window = TIME_RANGES.get(time_range or "all")
        base_filters = self._base_filters(
            auth_type=API_KEY_AUTH_TYPE, task_types=task_types, inference_only=True,
        )
        query = self._windowed_query(window, base_filters)
        aggregations = await self._os_client.aggregate(
            query, {"tenants": {"terms": {"field": "tenant_id", "size": 10000}}}
        )
        buckets = aggregations.get("tenants", {}).get("buckets", [])
        rows = [
            {"metric": {"tenant_id": b["key"], "tenant": ""}, "value": [0, b["doc_count"]]}
            for b in buckets if b["doc_count"] > 0
        ]
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
        }

    async def tenant_ranking(
        self, limit: int, time_range: Optional[str], tenant: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> dict:
        window = TIME_RANGES.get(time_range or "all")
        base_filters = self._base_filters(
            tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE, inference_only=True,
        )
        query = self._windowed_query(window, base_filters)
        aggregations = await self._os_client.aggregate(
            query, {"tenants": {"terms": {"field": "tenant_id", "size": 10000}}}
        )
        buckets = aggregations.get("tenants", {}).get("buckets", [])
        rows = [
            {"metric": {"tenant_id": b["key"], "tenant": ""}, "value": [0, b["doc_count"]]}
            for b in buckets if b["doc_count"] > 0
        ]
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

    async def usage_by_tenant_service(
        self,
        limit: int,
        time_range: Optional[str],
        services: Optional[list[str]],
        tenant: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> dict:
        active_services = services or list(SERVICE_BREAKDOWN_CONFIG)
        window = TIME_RANGES.get(time_range or "all")
        base_filters = self._base_filters(
            tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE, inference_only=True,
        )
        query = self._windowed_query(window, base_filters)

        buckets = await self._os_client.composite_all(
            query,
            sources=[
                {"tenant_id": {"terms": {"field": "tenant_id"}}},
                {"path": {"terms": {"field": "path"}}},
            ],
        )
        # Reshaped into Prometheus's own `sum by(tenant_id, tenant, endpoint)`
        # row shape so _accumulate_tenant_task_counts (inherited, unchanged)
        # can consume it exactly as it does the Prometheus result vector.
        results = [
            {
                "metric": {
                    "tenant_id": b["key"]["tenant_id"],
                    "tenant": "",
                    PROMETHEUS_API_PATH_LABEL: b["key"]["path"],
                },
                "value": [0, b["doc_count"]],
            }
            for b in buckets
        ]
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

    async def model_usage_growth_pct(self) -> Optional[float]:
        """Overall LLM request volume, current calendar month-to-date vs the
        previous calendar month — same KPI #7 semantics as the Prometheus
        version, exact counts instead of increase() extrapolation, and no
        PROMETHEUS_RETENTION_DAYS-style guard needed: the ISM policy
        (infrastructure/opensearch/ism-policy-logs.json, 90-day floor) is
        logs-*'s retention control and already covers this ~60-day lookback.
        """
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elapsed_s = int((now - month_start).total_seconds())
        if elapsed_s < 60:
            return None

        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
        prev_month_end = prev_month_start + timedelta(seconds=elapsed_s)

        filters = self._base_filters(auth_type=API_KEY_AUTH_TYPE, inference_only=True)
        filters.append({"terms": {"path": _LLM_CHAT_PATHS}})

        cur_query = {"bool": {"filter": [
            {"range": {"@timestamp": {"gte": month_start.isoformat(), "lte": now.isoformat()}}},
            *filters,
        ]}}
        prev_query = {"bool": {"filter": [
            {"range": {"@timestamp": {
                "gte": prev_month_start.isoformat(), "lt": prev_month_end.isoformat(),
            }}},
            *filters,
        ]}}

        try:
            cur_v, prev_v = await asyncio.gather(
                self._os_client.count(cur_query),
                self._os_client.count(prev_query),
            )
        except Exception:
            logger.warning("model_usage_growth_pct: OpenSearch query failed", exc_info=True)
            return None

        prev_total = max(0, prev_v)
        cur_total = max(0, cur_v)
        if prev_total <= 0:
            return None
        return round((cur_total - prev_total) / prev_total * 100, 1)

    async def service_breakdown(
        self, tenant: Optional[str], time_range: Optional[str],
        service_filter: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> dict:
        """Per-service stats: requests/success % from OpenSearch (exact
        counts), native units still from Prometheus via the inherited
        `_native_unit_queries`/`_unpack_native_units` — those metrics aren't
        part of this migration (doc §9) and `self._client` here is a real
        PrometheusClient for exactly this reason (see class docstring).

        Note: `tenant` (org name) has no OpenSearch equivalent filter — only
        `tenant_id` is used; see `_base_filters`. The native-unit queries
        below still take `tenant` directly since they're unchanged
        Prometheus calls.
        """
        unit_map = await inference_type_cache.get_unit_map_standalone()

        window = TIME_RANGES.get(time_range or "all")
        base_filters = self._base_filters(
            tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE,
            task_types=service_filter, inference_only=True,
        )
        query = self._windowed_query(window, base_filters)
        aggregations = await self._os_client.aggregate(query, {
            "by_path": {
                "terms": {"field": "path", "size": 1000},
                "aggs": {"by_status": self._status_filters_agg()},
            }
        })
        buckets = aggregations.get("by_path", {}).get("buckets", [])

        # Reshaped into the same `{"metric": {endpoint_label: path}, "value":
        # [_, count]}` row shape Prometheus's `sum by(endpoint)` result uses,
        # so _endpoint_dict (inherited, unchanged) can resolve path -> task
        # key exactly as it already does for the Prometheus path.
        total_rows = [
            {"metric": {PROMETHEUS_API_PATH_LABEL: b["key"]}, "value": [0, b["doc_count"]]}
            for b in buckets
        ]
        success_rows = [
            {
                "metric": {PROMETHEUS_API_PATH_LABEL: b["key"]},
                "value": [0, b.get("by_status", {}).get("buckets", {}).get("success", {}).get("doc_count", 0)],
            }
            for b in buckets
        ]
        totals = self._endpoint_dict(total_rows)
        successes = self._endpoint_dict(success_rows)

        native_tasks, native_coros = self._native_unit_queries(
            tenant, time_range, service_filter, tenant_id=tenant_id,
        )
        native_raw = await asyncio.gather(*native_coros, return_exceptions=True)
        natives = self._unpack_native_units(native_tasks, native_raw, native_offset=0)

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
        """Per-service AND per-model requests/success % from OpenSearch (exact
        counts, via a `composite` aggregation over `service_id`/`model_id`/
        `path` — doc §7.9), native units still from Prometheus. All the
        ghost-filtering/rollup logic (registry validation, the independent
        per-service vs. per-model views) is unchanged — see
        `MeteringService._shape_model_breakdown`, extracted specifically so
        this override can reuse it without touching a single line of that
        logic.

        `missing_bucket: true` on the `model_id` composite source matters:
        RequestMiddleware only logs a field when it's truthy (see
        ai4i_core's ctx-enrichment loop), so a request whose service_id
        resolved but whose model_id didn't (or wasn't set) has NO `model_id`
        field on its log line at all — unlike Prometheus, where the label
        always exists on the series, just possibly as `""`. Without
        `missing_bucket`, OpenSearch's composite aggregation would silently
        exclude those documents entirely, undercounting that service's
        request total; with it, they get their own bucket (model_id=None),
        preserving the per-service total exactly the way `_effective_model_id`
        already expects (empty/`None` model_id is `""`, filtered out of the
        model-level view but NOT the service-level one).
        """
        unit_map = await inference_type_cache.get_unit_map_standalone()
        window = TIME_RANGES.get(time_range or "all")
        base_filters = self._base_filters(
            tenant_id=tenant_id, auth_type=API_KEY_AUTH_TYPE,
            task_types=task_types, inference_only=True,
        )
        query = self._windowed_query(window, base_filters)

        buckets = await self._os_client.composite_all(
            query,
            sources=[
                {"service_id": {"terms": {"field": "service_id"}}},
                {"model_id": {"terms": {"field": "model_id", "missing_bucket": True}}},
                {"path": {"terms": {"field": "path"}}},
            ],
            sub_aggs={"by_status": self._status_filters_agg()},
        )

        # Reshaped into Prometheus's own `sum by(service_id, model_id,
        # endpoint)` row shape so _shape_model_breakdown (inherited,
        # unchanged) can consume it exactly as it does the Prometheus result
        # vector — see this method's own docstring above.
        total_rows: list[dict] = []
        success_rows: list[dict] = []
        for b in buckets:
            key = b["key"]
            metric = {
                "service_id": key.get("service_id") or "",
                "model_id": key.get("model_id") or "",
                PROMETHEUS_API_PATH_LABEL: key.get("path") or "",
            }
            total_rows.append({"metric": metric, "value": [0, b["doc_count"]]})
            success_count = b.get("by_status", {}).get("buckets", {}).get("success", {}).get("doc_count", 0)
            success_rows.append({"metric": metric, "value": [0, success_count]})

        native_tasks, native_coros = self._model_native_unit_queries(
            tenant, tenant_id, time_range, task_types,
        )
        native_raw = await asyncio.gather(*native_coros, return_exceptions=True)
        native_by_task: dict[str, dict[str, float]] = {
            task: self._native_units_by_service(native_raw[i] if not isinstance(native_raw[i], Exception) else [])
            for i, task in enumerate(native_tasks)
        }

        return await self._shape_model_breakdown(
            total_rows, success_rows, native_by_task, unit_map, tenant, time_range, task_types,
        )
