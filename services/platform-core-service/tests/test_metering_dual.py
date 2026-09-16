"""Unit tests for DualMeteringService (app/services/metering_service_dual.py):
computes both Prometheus and OpenSearch results, logs the delta, and always
serves Prometheus's outcome (success or failure) regardless of what
OpenSearch did.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.metering_service_dual import DualMeteringService
from app.utils.metering_promql_builder import PROMETHEUS_API_PATH_LABEL


def _make_dual_service():
    prom_client = MagicMock()
    prom_client.query = AsyncMock(return_value=[])
    prom_client.scalar = AsyncMock(return_value=0.0)
    prom_client.query_range = AsyncMock(return_value=[])

    os_client = MagicMock()
    os_client.aggregate = AsyncMock(return_value={})
    os_client.count = AsyncMock(return_value=0)
    os_client.composite_all = AsyncMock(return_value=[])

    return DualMeteringService(os_client=os_client, client=prom_client)


@pytest.mark.asyncio
class TestDualCallServesPrometheus:
    async def test_returns_prometheus_result_even_when_it_differs_from_opensearch(self):
        svc = _make_dual_service()
        prom_coro = AsyncMock(return_value={"value": 1})()
        os_coro = AsyncMock(return_value={"value": 2})()
        with patch.object(svc, "_log_delta") as mock_log:
            result = await svc._dual_call("some_kpi", prom_coro, os_coro)
        assert result == {"value": 1}
        mock_log.assert_called_once_with("some_kpi", {"value": 1}, {"value": 2})

    async def test_reraises_prometheus_exception_even_when_opensearch_succeeds(self):
        svc = _make_dual_service()

        async def _prom():
            raise RuntimeError("prometheus down")

        async def _os():
            return {"value": 2}

        with pytest.raises(RuntimeError, match="prometheus down"):
            await svc._dual_call("some_kpi", _prom(), _os())

    async def test_opensearch_exception_does_not_affect_prometheus_result(self):
        svc = _make_dual_service()

        async def _prom():
            return {"value": 1}

        async def _os():
            raise RuntimeError("opensearch down")

        result = await svc._dual_call("some_kpi", _prom(), _os())
        assert result == {"value": 1}

    async def test_both_sides_run_concurrently_not_sequentially(self):
        """A slow OpenSearch call must not block the Prometheus result from
        being computed — asyncio.gather, not sequential awaits."""
        import asyncio
        svc = _make_dual_service()
        order = []

        async def _prom():
            order.append("prom_start")
            await asyncio.sleep(0)
            order.append("prom_end")
            return {"value": 1}

        async def _os():
            order.append("os_start")
            await asyncio.sleep(0)
            order.append("os_end")
            return {"value": 1}

        await svc._dual_call("k", _prom(), _os())
        assert order[0] == "prom_start" and order[1] == "os_start"


class TestLogDelta:
    def test_matching_summaries_logged_at_info(self, caplog):
        svc = _make_dual_service()
        import logging
        with caplog.at_level(logging.INFO, logger="app.services.metering_service_dual"):
            svc._log_delta(
                "request_total",
                {"total_requests": {"count": 10}, "successful_requests": {"count": 9}, "failed_requests": {"count": 1}},
                {"total_requests": {"count": 10}, "successful_requests": {"count": 9}, "failed_requests": {"count": 1}},
            )
        assert any("match" in r.message for r in caplog.records)
        assert not any("DELTA" in r.message for r in caplog.records)

    def test_differing_summaries_logged_at_warning(self, caplog):
        svc = _make_dual_service()
        import logging
        with caplog.at_level(logging.WARNING, logger="app.services.metering_service_dual"):
            svc._log_delta(
                "request_total",
                {"total_requests": {"count": 10}, "successful_requests": {"count": 9}, "failed_requests": {"count": 1}},
                {"total_requests": {"count": 8}, "successful_requests": {"count": 7}, "failed_requests": {"count": 1}},
            )
        assert any("DELTA" in r.message for r in caplog.records)

    def test_exception_on_either_side_logs_warning_without_crashing(self, caplog):
        svc = _make_dual_service()
        import logging
        with caplog.at_level(logging.WARNING, logger="app.services.metering_service_dual"):
            svc._log_delta("request_total", RuntimeError("boom"), {"total_requests": {"count": 1}})
        assert any("query failed" in r.message for r in caplog.records)

    def test_unrecognized_kpi_name_skips_comparison_without_error(self):
        svc = _make_dual_service()
        # Should not raise even though "unknown_kpi" has no extractor.
        svc._log_delta("unknown_kpi", {"anything": 1}, {"anything": 2})


@pytest.mark.asyncio
class TestRequestTotalDualRun:
    async def test_calls_both_backends_and_serves_prometheus_shape(self):
        svc = _make_dual_service()
        svc._client.query = AsyncMock(return_value=[])
        svc._client.scalar = AsyncMock(return_value=5.0)
        svc._os_client.aggregate = AsyncMock(return_value={
            "by_period": {"buckets": {
                "current": {"doc_count": 3, "by_status": {"buckets": {"success": {"doc_count": 3}, "failed": {"doc_count": 0}}}},
                "previous": {"doc_count": 0, "by_status": {"buckets": {}}},
            }}
        })
        result = await svc.request_total(
            inference_only=True, tenant=None, service_id=None, time_range="24h",
        )
        # Result shape/values come from the Prometheus side (scalar_return=5.0 everywhere).
        assert result["total_requests"]["count"] == 5
        svc._os_client.aggregate.assert_called_once()


@pytest.mark.asyncio
class TestServiceBreakdownDualRun:
    async def test_calls_both_backends_and_serves_prometheus_shape(self):
        svc = _make_dual_service()
        svc._client.query = AsyncMock(return_value=[
            {"metric": {PROMETHEUS_API_PATH_LABEL: "/api/v1/nmt/inference"}, "value": [0, "5"]},
        ])
        svc._os_client.aggregate = AsyncMock(return_value={"by_path": {"buckets": [
            {"key": "/api/v1/nmt/inference", "doc_count": 999,
             "by_status": {"buckets": {"success": {"doc_count": 999}, "failed": {"doc_count": 0}}}},
        ]}})
        result = await svc.service_breakdown(tenant=None, time_range="24h")
        # Served value (5) comes from Prometheus's mocked query(), not the
        # OpenSearch side's 999 — confirms Prometheus is still authoritative.
        nmt = next(s for s in result["services"] if s["service"] == "NMT")
        assert nmt["requests"] == 5
        svc._os_client.aggregate.assert_called_once()


@pytest.mark.asyncio
class TestModelBreakdownDualRun:
    async def test_calls_both_backends_and_serves_prometheus_shape(self):
        svc = _make_dual_service()
        svc._client.query = AsyncMock(return_value=[
            {"metric": {"service_id": "svc-1", "model_id": "m-1", PROMETHEUS_API_PATH_LABEL: "/api/v1/chat"}, "value": [0, "5"]},
        ])
        svc._os_client.composite_all = AsyncMock(return_value=[
            {
                "key": {"service_id": "svc-1", "model_id": "m-1", "path": "/api/v1/chat"},
                "doc_count": 999,
                "by_status": {"buckets": {"success": {"doc_count": 999}, "failed": {"doc_count": 0}}},
            },
        ])
        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "svc-1")
        # Served value (5) comes from Prometheus's mocked query(), not the
        # OpenSearch side's 999.
        assert row["requests"] == 5
        svc._os_client.composite_all.assert_called_once()


@pytest.mark.asyncio
class TestOverviewTenantDataUsesDualActiveTenants:
    async def test_overview_tenant_data_dispatches_through_dual_active_tenants(self):
        """overview_tenant_data (inherited, unmodified) calls self.active_tenants
        internally — on a DualMeteringService instance that must resolve to
        THIS class's dual-run override, not silently fall back to Prometheus-only."""
        svc = _make_dual_service()
        svc._auth_db = None  # tenant_count()/_fetch_valid_tenant_ids() degrade cleanly
        with patch.object(svc, "active_tenants", wraps=svc.active_tenants) as spy:
            await svc.overview_tenant_data(["24h"])
        assert spy.called
