"""Dual-run MeteringService — computes every migrated request-count KPI from
BOTH Prometheus and OpenSearch on every call, logs the delta, and always
serves Prometheus's numbers.

This is the code side of the rollout plan's dual-run step: compare the two
stores for >=30 days per tab before trusting OpenSearch's numbers (arch-docs/
3055-metering-opensearch-request-counts.md §10 step 4). It is NOT a new
computation path — it composes the two existing services
(MeteringService, OpenSearchMeteringService) and never lets an OpenSearch
failure or disagreement affect what the caller gets back.

Subclasses OpenSearchMeteringService (not MeteringService directly) so it
inherits the OpenSearch overrides needed to call
`OpenSearchMeteringService.<method>(self, ...)` explicitly for the OpenSearch
side of each comparison, while `MeteringService.<method>(self, ...)` is
called explicitly for the Prometheus side — both bound to the same `self`,
which carries both a real Prometheus client (`self._client`) and a real
OpenSearch client (`self._os_client`), exactly like OpenSearchMeteringService
already requires.

Methods NOT overridden here (service_breakdown, model_breakdown,
tenant_count, registry_model_count, model_consumption_ranking,
model_consumption_kpis, overview_tenant_data) are inherited from
MeteringService via OpenSearchMeteringService and run Prometheus-only, same
as in plain "opensearch" mode — there's nothing to dual-run for them yet.
`overview_tenant_data` needs no override of its own: it calls
`self.active_tenants(...)` internally, which resolves polymorphically to
this class's dual-run override.
"""
import asyncio
import logging
from typing import Optional, Union

from app.schemas.metering import Graph
from app.services.metering_service import MeteringService, _UNSET, _Unset
from app.services.metering_service_opensearch import OpenSearchMeteringService

logger = logging.getLogger(__name__)


def _request_total_summary(r: dict) -> dict:
    return {
        "total": r["total_requests"]["count"],
        "success": r["successful_requests"]["count"],
        "failed": r["failed_requests"]["count"],
    }


def _request_volume_chart_summary(r: Optional[Graph]) -> dict:
    if r is None:
        return {"empty": True}
    totals = {s.key: sum(p.value for p in s.points) for s in r.series}
    return {"successful_total": totals.get("successful", 0), "failed_total": totals.get("failed", 0)}


# Per-method extractor of the small set of numbers worth comparing —
# deliberately not a fully generic diff (doc §11: this is for a human to
# read during the dual-run window, not automated alerting yet).
_COMPARABLE: dict = {
    "request_total": _request_total_summary,
    "request_volume_chart": _request_volume_chart_summary,
    "active_tenants": lambda r: {"count": r["count"]},
    "active_tenants_count_previous": lambda r: {"count": r},
    "avg_per_active_tenant_previous": lambda r: {"avg": r},
    "usage_concentration": lambda r: {"grand_total": r["grand_total"]},
    "tenant_ranking": lambda r: {"grand_total": r["grand_total"], "tenant_count": r["total_tenant_count"]},
    "usage_by_tenant_service": lambda r: {"grand_total": r["grand_total"], "tenant_count": r["total_tenant_count"]},
    "model_usage_growth_pct": lambda r: {"pct": r},
}


class DualMeteringService(OpenSearchMeteringService):
    @staticmethod
    def _summarize(name: str, result) -> Optional[dict]:
        extractor = _COMPARABLE.get(name)
        if extractor is None:
            return None
        try:
            return extractor(result)
        except Exception:
            return None

    def _log_delta(self, name: str, prom_result, os_result) -> None:
        prom_failed = isinstance(prom_result, Exception)
        os_failed = isinstance(os_result, Exception)
        if prom_failed or os_failed:
            logger.warning(
                "metering dual-run %s: query failed (prometheus_error=%s, opensearch_error=%s)",
                name,
                repr(prom_result) if prom_failed else None,
                repr(os_result) if os_failed else None,
            )
            return

        prom_summary = self._summarize(name, prom_result)
        os_summary = self._summarize(name, os_result)
        if prom_summary is None or os_summary is None:
            return
        if prom_summary != os_summary:
            logger.warning(
                "metering dual-run %s: DELTA prometheus=%s opensearch=%s", name, prom_summary, os_summary,
            )
        else:
            logger.info("metering dual-run %s: match %s", name, prom_summary)

    async def _dual_call(self, name: str, prom_coro, os_coro):
        """Run both coroutines concurrently, log the comparison, and return
        (or re-raise) ONLY the Prometheus outcome — an OpenSearch failure or
        disagreement must never surface to the caller during dual-run."""
        prom_result, os_result = await asyncio.gather(prom_coro, os_coro, return_exceptions=True)
        self._log_delta(name, prom_result, os_result)
        if isinstance(prom_result, Exception):
            raise prom_result
        return prom_result

    # ── dual-run overrides (one per migrated KPI) ───────────────────────

    async def request_total(
        self, inference_only, tenant, service_id, time_range,
        task_types=None, tenant_id=None, auth_type=None,
    ) -> dict:
        return await self._dual_call(
            "request_total",
            MeteringService.request_total(
                self, inference_only, tenant, service_id, time_range, task_types, tenant_id, auth_type,
            ),
            OpenSearchMeteringService.request_total(
                self, inference_only, tenant, service_id, time_range, task_types, tenant_id, auth_type,
            ),
        )

    async def request_volume_chart(
        self, window, tenant, task_types=None, tenant_id=None, auth_type=None,
    ) -> Optional[Graph]:
        return await self._dual_call(
            "request_volume_chart",
            MeteringService.request_volume_chart(self, window, tenant, task_types, tenant_id, auth_type),
            OpenSearchMeteringService.request_volume_chart(self, window, tenant, task_types, tenant_id, auth_type),
        )

    async def active_tenants(
        self, time_range: Optional[str], valid_names: Union[set, None, _Unset] = _UNSET
    ) -> dict:
        return await self._dual_call(
            "active_tenants",
            MeteringService.active_tenants(self, time_range, valid_names),
            OpenSearchMeteringService.active_tenants(self, time_range, valid_names),
        )

    async def active_tenants_count_previous(self, time_range: Optional[str]) -> Optional[int]:
        return await self._dual_call(
            "active_tenants_count_previous",
            MeteringService.active_tenants_count_previous(self, time_range),
            OpenSearchMeteringService.active_tenants_count_previous(self, time_range),
        )

    async def avg_per_active_tenant_previous(
        self, time_range: Optional[str], tenant: Optional[str] = None, tenant_id: Optional[str] = None,
    ) -> Optional[int]:
        return await self._dual_call(
            "avg_per_active_tenant_previous",
            MeteringService.avg_per_active_tenant_previous(self, time_range, tenant, tenant_id),
            OpenSearchMeteringService.avg_per_active_tenant_previous(self, time_range, tenant, tenant_id),
        )

    async def usage_concentration(
        self, limit: int, time_range: Optional[str], task_types: Optional[list[str]] = None,
    ) -> dict:
        return await self._dual_call(
            "usage_concentration",
            MeteringService.usage_concentration(self, limit, time_range, task_types),
            OpenSearchMeteringService.usage_concentration(self, limit, time_range, task_types),
        )

    async def tenant_ranking(
        self, limit: int, time_range: Optional[str], tenant: Optional[str] = None, tenant_id: Optional[str] = None,
    ) -> dict:
        return await self._dual_call(
            "tenant_ranking",
            MeteringService.tenant_ranking(self, limit, time_range, tenant, tenant_id),
            OpenSearchMeteringService.tenant_ranking(self, limit, time_range, tenant, tenant_id),
        )

    async def usage_by_tenant_service(
        self, limit: int, time_range: Optional[str], services: Optional[list[str]],
        tenant: Optional[str] = None, tenant_id: Optional[str] = None,
    ) -> dict:
        return await self._dual_call(
            "usage_by_tenant_service",
            MeteringService.usage_by_tenant_service(self, limit, time_range, services, tenant, tenant_id),
            OpenSearchMeteringService.usage_by_tenant_service(self, limit, time_range, services, tenant, tenant_id),
        )

    async def model_usage_growth_pct(self) -> Optional[float]:
        return await self._dual_call(
            "model_usage_growth_pct",
            MeteringService.model_usage_growth_pct(self),
            OpenSearchMeteringService.model_usage_growth_pct(self),
        )
