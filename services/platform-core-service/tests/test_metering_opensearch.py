"""Unit tests for the OpenSearch-backed metering query layer:
OpenSearchLogClient (app/utils/opensearch_log_client.py) and
OpenSearchMeteringService (app/services/metering_service_opensearch.py).

All OpenSearch I/O is mocked — no running cluster required. Mirrors
test_metering.py's conventions (AsyncMock/MagicMock, no live services).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.metering_service_opensearch import (
    OpenSearchMeteringService,
    _task_type_paths,
)
from app.utils.opensearch_log_client import OpenSearchLogClient


# ── OpenSearchLogClient ──────────────────────────────────────────────────────


def _client_with_search(return_value=None, side_effect=None):
    client = OpenSearchLogClient.__new__(OpenSearchLogClient)
    client.index = "logs-*"
    client._client = MagicMock()
    if side_effect is not None:
        client._client.search = MagicMock(side_effect=side_effect)
    else:
        client._client.search = MagicMock(return_value=return_value or {})
    return client


@pytest.mark.asyncio
class TestOpenSearchLogClientCount:
    async def test_count_reads_track_total_hits_value(self):
        client = _client_with_search({"hits": {"total": {"value": 42}}})
        result = await client.count({"match_all": {}})
        assert result == 42
        body = client._client.search.call_args.kwargs["body"]
        assert body["track_total_hits"] is True
        assert body["size"] == 0

    async def test_count_returns_zero_on_missing_hits(self):
        client = _client_with_search({})
        assert await client.count({"match_all": {}}) == 0

    async def test_search_failure_returns_empty_dict_not_raise(self):
        client = _client_with_search(side_effect=RuntimeError("cluster down"))
        assert await client.count({"match_all": {}}) == 0


@pytest.mark.asyncio
class TestOpenSearchLogClientAggregate:
    async def test_returns_aggregations_key(self):
        client = _client_with_search({"aggregations": {"tenants": {"buckets": [{"key": "1", "doc_count": 5}]}}})
        aggs = await client.aggregate({"match_all": {}}, {"tenants": {"terms": {"field": "tenant_id"}}})
        assert aggs["tenants"]["buckets"][0]["key"] == "1"

    async def test_missing_aggregations_key_is_empty_dict(self):
        client = _client_with_search({"hits": {"total": {"value": 0}}})
        aggs = await client.aggregate({"match_all": {}}, {})
        assert aggs == {}


@pytest.mark.asyncio
class TestOpenSearchLogClientCompositeAll:
    async def test_single_page_no_after_key(self):
        client = _client_with_search({
            "aggregations": {"buckets": {"buckets": [
                {"key": {"tenant_id": "1"}, "doc_count": 3},
                {"key": {"tenant_id": "2"}, "doc_count": 7},
            ]}}
        })
        buckets = await client.composite_all({"match_all": {}}, sources=[{"tenant_id": {"terms": {"field": "tenant_id"}}}])
        assert len(buckets) == 2
        assert client._client.search.call_count == 1

    async def test_paginates_via_after_key_until_exhausted(self):
        page1 = {"aggregations": {"buckets": {
            "buckets": [{"key": {"tenant_id": "1"}, "doc_count": 1}],
            "after_key": {"tenant_id": "1"},
        }}}
        page2 = {"aggregations": {"buckets": {
            "buckets": [{"key": {"tenant_id": "2"}, "doc_count": 2}],
            # no after_key -> last page
        }}}
        client = _client_with_search(side_effect=[page1, page2])
        buckets = await client.composite_all({"match_all": {}}, sources=[{"tenant_id": {"terms": {"field": "tenant_id"}}}])
        assert [b["key"]["tenant_id"] for b in buckets] == ["1", "2"]
        assert client._client.search.call_count == 2
        # second request must carry the after_key from the first page
        second_body = client._client.search.call_args_list[1].kwargs["body"]
        assert second_body["aggs"]["buckets"]["composite"]["after"] == {"tenant_id": "1"}

    async def test_stops_at_max_pages_even_if_after_key_keeps_coming(self):
        page = {"aggregations": {"buckets": {
            "buckets": [{"key": {"tenant_id": "x"}, "doc_count": 1}],
            "after_key": {"tenant_id": "x"},
        }}}
        client = _client_with_search(side_effect=[page, page, page])
        buckets = await client.composite_all(
            {"match_all": {}}, sources=[{"tenant_id": {"terms": {"field": "tenant_id"}}}], max_pages=3,
        )
        assert client._client.search.call_count == 3
        assert len(buckets) == 3

    async def test_no_buckets_stops_immediately(self):
        client = _client_with_search({"aggregations": {"buckets": {"buckets": []}}})
        buckets = await client.composite_all({"match_all": {}}, sources=[{"tenant_id": {"terms": {"field": "tenant_id"}}}])
        assert buckets == []
        assert client._client.search.call_count == 1


# ── OpenSearchMeteringService ────────────────────────────────────────────────


def _make_os_service(
    aggregate_return=None, count_return=0, composite_return=None, auth_db=None,
    prom_client=None,
):
    os_client = MagicMock()
    os_client.aggregate = AsyncMock(return_value=aggregate_return if aggregate_return is not None else {})
    os_client.count = AsyncMock(return_value=count_return)
    os_client.composite_all = AsyncMock(return_value=composite_return or [])
    return (
        OpenSearchMeteringService(os_client=os_client, client=prom_client, auth_db=auth_db),
        os_client,
    )


def _mock_prom_client(scalar_return=0.0):
    client = MagicMock()
    client.scalar = AsyncMock(return_value=scalar_return)
    client.query = AsyncMock(return_value=[])
    client.query_range = AsyncMock(return_value=[])
    return client


class TestTaskTypePaths:
    def test_llm_maps_to_literal_chat_paths(self):
        assert _task_type_paths(["llm"]) == ["/api/v1/chat", "/api/v1/chat/completions"]

    def test_standard_task_builds_inference_path(self):
        assert _task_type_paths(["nmt"]) == ["/api/v1/nmt/inference"]

    def test_hyphenated_task_underscore_to_hyphen(self):
        assert _task_type_paths(["speaker_diarization"]) == ["/api/v1/speaker-diarization/inference"]


class TestBaseFilters:
    def test_tenant_id_and_service_id_are_term_filters(self):
        filters = OpenSearchMeteringService._base_filters(
            tenant_id="42", service_id="svc-1", inference_only=False,
        )
        assert {"term": {"tenant_id": "42"}} in filters
        assert {"term": {"service_id": "svc-1"}} in filters

    def test_auth_type_is_fail_open(self):
        filters = OpenSearchMeteringService._base_filters(auth_type="api_key", inference_only=False)
        (clause,) = filters
        shoulds = clause["bool"]["should"]
        assert {"term": {"auth_type": "api_key"}} in shoulds
        assert {"bool": {"must_not": {"exists": {"field": "auth_type"}}}} in shoulds

    def test_inference_only_without_task_types_matches_inference_suffix_and_chat(self):
        filters = OpenSearchMeteringService._base_filters(inference_only=True)
        (clause,) = filters
        shoulds = clause["bool"]["should"]
        assert {"wildcard": {"path": "*/inference"}} in shoulds

    def test_task_types_narrows_to_literal_paths(self):
        filters = OpenSearchMeteringService._base_filters(inference_only=True, task_types=["nmt"])
        assert {"terms": {"path": ["/api/v1/nmt/inference"]}} in filters

    def test_no_tenant_name_filter_exists(self):
        """OpenSearch only ever filters on tenant_id — there is no `tenant`
        (org name) field on the log line to filter on."""
        filters = OpenSearchMeteringService._base_filters(inference_only=False)
        assert filters == []


class TestDoubleWindow:
    @pytest.mark.parametrize("window,expected", [("1h", "2h"), ("24h", "48h"), ("7d", "14d"), ("30d", "60d")])
    def test_doubles_numeric_part(self, window, expected):
        assert OpenSearchMeteringService._double_window(window) == expected


@pytest.mark.asyncio
class TestRequestTotal:
    async def test_windowed_computes_all_fields_from_one_aggregation(self):
        svc, os_client = _make_os_service(aggregate_return={
            "by_period": {"buckets": {
                "current": {"doc_count": 100, "by_status": {"buckets": {
                    "success": {"doc_count": 90}, "failed": {"doc_count": 10},
                }}},
                "previous": {"doc_count": 50, "by_status": {"buckets": {
                    "success": {"doc_count": 40}, "failed": {"doc_count": 10},
                }}},
            }}
        })
        result = await svc.request_total(
            inference_only=True, tenant=None, service_id=None, time_range="24h",
        )
        assert result["total_requests"]["count"] == 100
        assert result["successful_requests"]["count"] == 90
        assert result["failed_requests"]["count"] == 10
        assert result["success_rate"]["rate_pct"] == 90.0
        assert result["total_requests"]["vs_previous_pct"] == 100.0  # 100 vs 50 -> +100%
        assert result["total_requests"]["previous_count"] == 50
        assert result["avg_rps"]["value"] == round(100 / 86400, 4)
        # Only ONE OpenSearch round trip for the whole current+previous computation.
        os_client.aggregate.assert_called_once()

    async def test_windowed_no_previous_traffic_vs_prev_is_none(self):
        svc, _ = _make_os_service(aggregate_return={
            "by_period": {"buckets": {
                "current": {"doc_count": 5, "by_status": {"buckets": {
                    "success": {"doc_count": 5}, "failed": {"doc_count": 0},
                }}},
                "previous": {"doc_count": 0, "by_status": {"buckets": {}}},
            }}
        })
        result = await svc.request_total(inference_only=True, tenant=None, service_id=None, time_range="1h")
        assert result["total_requests"]["vs_previous_pct"] is None
        assert result["total_requests"]["previous_count"] == 0

    async def test_unwindowed_all_uses_count_and_five_minute_rate(self):
        svc, os_client = _make_os_service(
            count_return=1000,
            aggregate_return={"by_status": {"buckets": {"success": {"doc_count": 900}, "failed": {"doc_count": 100}}}},
        )
        result = await svc.request_total(inference_only=True, tenant=None, service_id=None, time_range=None)
        assert result["total_requests"]["count"] == 1000
        assert result["successful_requests"]["count"] == 900
        assert result["total_requests"]["vs_previous_pct"] is None
        assert result["total_requests"]["previous_count"] is None
        # avg_rps = five_min_total(1000, from the same mocked count()) / 300
        assert result["avg_rps"]["value"] == round(1000 / 300, 4)


@pytest.mark.asyncio
class TestRequestVolumeChart:
    async def test_unknown_window_returns_none(self):
        svc, _ = _make_os_service()
        assert await svc.request_volume_chart("5m", tenant=None) is None

    async def test_no_data_anywhere_returns_none(self):
        svc, _ = _make_os_service(aggregate_return={"over_time": {"buckets": [
            {"key": 1000, "by_status": {"buckets": {"success": {"doc_count": 0}, "failed": {"doc_count": 0}}}},
        ]}})
        assert await svc.request_volume_chart("24h", tenant=None) is None

    async def test_builds_dense_success_and_failed_series(self):
        svc, os_client = _make_os_service(aggregate_return={"over_time": {"buckets": [
            {"key": 1_700_000_000_000, "by_status": {"buckets": {
                "success": {"doc_count": 3}, "failed": {"doc_count": 1},
            }}},
        ]}})
        chart = await svc.request_volume_chart("24h", tenant=None)
        assert chart is not None
        assert chart.step == "4h"
        by_key = {s.key: s for s in chart.series}
        assert by_key["successful"].points[0].value == 3
        assert by_key["successful"].points[0].ts == 1_700_000_000
        assert by_key["failed"].points[0].value == 1


@pytest.mark.asyncio
class TestActiveTenants:
    async def test_merges_and_resolves_names_when_valid_names_unset(self):
        svc, os_client = _make_os_service(
            aggregate_return={"tenants": {"buckets": [
                {"key": "1", "doc_count": 10}, {"key": "2", "doc_count": 5},
            ]}},
        )
        svc._fetch_valid_tenant_ids = AsyncMock(return_value=None)
        svc._resolve_tenant_names = AsyncMock(return_value={"1": "Acme"})
        result = await svc.active_tenants("24h")
        tenants_by_id = {t["tenant"]: t["request_count"] for t in result["active_tenants"]}
        assert tenants_by_id["Acme"] == 10
        assert result["count"] == 2

    async def test_filters_out_tenants_not_in_valid_names(self):
        svc, os_client = _make_os_service(
            aggregate_return={"tenants": {"buckets": [
                {"key": "1", "doc_count": 10}, {"key": "2", "doc_count": 5},
            ]}},
        )
        result = await svc.active_tenants("24h", valid_names={"1"})
        assert result["count"] == 1

    async def test_does_not_call_fetch_valid_ids_when_names_explicitly_passed(self):
        svc, os_client = _make_os_service(aggregate_return={"tenants": {"buckets": []}})
        svc._fetch_valid_tenant_ids = AsyncMock(side_effect=AssertionError("should not be called"))
        await svc.active_tenants("24h", valid_names=None)


@pytest.mark.asyncio
class TestUsageConcentration:
    async def test_splits_top_n_and_others(self):
        svc, _ = _make_os_service(aggregate_return={"tenants": {"buckets": [
            {"key": "1", "doc_count": 100},
            {"key": "2", "doc_count": 50},
            {"key": "3", "doc_count": 10},
        ]}})
        svc._resolve_tenant_names = AsyncMock(return_value={"1": "A", "2": "B", "3": "C"})
        result = await svc.usage_concentration(limit=2, time_range="24h")
        assert [t["tenant"] for t in result["top_tenants"]] == ["A", "B"]
        assert result["others"]["count"] == 1
        assert result["others"]["requests"] == 10
        assert result["grand_total"] == 160


@pytest.mark.asyncio
class TestTenantRanking:
    async def test_computes_avg_per_active_tenant(self):
        svc, _ = _make_os_service(aggregate_return={"tenants": {"buckets": [
            {"key": "1", "doc_count": 30}, {"key": "2", "doc_count": 10},
        ]}})
        svc._resolve_tenant_names = AsyncMock(return_value={"1": "A", "2": "B"})
        result = await svc.tenant_ranking(limit=10, time_range="24h")
        assert result["grand_total"] == 40
        assert result["avg_per_active_tenant"] == 20
        assert result["total_tenant_count"] == 2


@pytest.mark.asyncio
class TestUsageByTenantService:
    async def test_composite_buckets_become_heatmap_rows(self):
        svc, os_client = _make_os_service(composite_return=[
            {"key": {"tenant_id": "1", "path": "/api/v1/nmt/inference"}, "doc_count": 7},
            {"key": {"tenant_id": "1", "path": "/api/v1/chat"}, "doc_count": 3},
        ])
        svc._resolve_tenant_names = AsyncMock(return_value={"1": "Acme"})
        result = await svc.usage_by_tenant_service(limit=10, time_range="24h", services=["nmt", "llm"])
        assert result["grand_total"] == 10
        row = result["tenants"][0]
        assert row["tenant"] == "Acme"
        assert row["services"]["nmt"]["requests"] == 7
        assert row["services"]["llm"]["requests"] == 3
        # composite_all called with a (tenant_id, path) source pair
        sources = os_client.composite_all.call_args.kwargs["sources"]
        assert sources[0]["tenant_id"]["terms"]["field"] == "tenant_id"
        assert sources[1]["path"]["terms"]["field"] == "path"


@pytest.mark.asyncio
class TestServiceBreakdown:
    async def test_request_counts_come_from_opensearch_terms_agg(self):
        prom_client = _mock_prom_client(scalar_return=0.0)
        svc, os_client = _make_os_service(
            prom_client=prom_client,
            aggregate_return={"by_path": {"buckets": [
                {
                    "key": "/api/v1/nmt/inference", "doc_count": 10,
                    "by_status": {"buckets": {"success": {"doc_count": 8}, "failed": {"doc_count": 2}}},
                },
                {
                    "key": "/api/v1/chat", "doc_count": 4,
                    "by_status": {"buckets": {"success": {"doc_count": 4}, "failed": {"doc_count": 0}}},
                },
            ]}},
        )
        result = await svc.service_breakdown(tenant=None, time_range="24h")
        by_service = {s["service"]: s for s in result["services"]}
        assert by_service["NMT"]["requests"] == 10
        assert by_service["NMT"]["success_pct"] == 80.0
        assert by_service["LLM"]["requests"] == 4
        assert by_service["LLM"]["success_pct"] == 100.0

    async def test_native_units_still_come_from_prometheus(self):
        prom_client = _mock_prom_client(scalar_return=42.0)
        svc, os_client = _make_os_service(
            prom_client=prom_client,
            aggregate_return={"by_path": {"buckets": [
                {
                    "key": "/api/v1/nmt/inference", "doc_count": 5,
                    "by_status": {"buckets": {"success": {"doc_count": 5}, "failed": {"doc_count": 0}}},
                },
            ]}},
        )
        result = await svc.service_breakdown(tenant=None, time_range="24h", service_filter=["nmt"])
        nmt = next(s for s in result["services"] if s["service"] == "NMT")
        assert nmt["native_units"] == 42
        # Native units are a Prometheus scalar() call, not an OpenSearch one.
        assert prom_client.scalar.called

    async def test_service_filter_limits_native_unit_queries(self):
        prom_client = _mock_prom_client(scalar_return=1.0)
        svc, _ = _make_os_service(prom_client=prom_client, aggregate_return={"by_path": {"buckets": []}})
        await svc.service_breakdown(tenant=None, time_range="24h", service_filter=["nmt"])
        # Only one native-unit metric (nmt) queried, not all of SERVICE_BREAKDOWN_CONFIG.
        assert prom_client.scalar.call_count == 1


@pytest.mark.asyncio
class TestModelBreakdown:
    def _bucket(self, service_id, model_id, path, total, success):
        return {
            "key": {"service_id": service_id, "model_id": model_id, "path": path},
            "doc_count": total,
            "by_status": {"buckets": {"success": {"doc_count": success}, "failed": {"doc_count": total - success}}},
        }

    async def test_groups_by_service_and_model_composite_buckets(self):
        prom_client = _mock_prom_client(scalar_return=0.0)
        svc, os_client = _make_os_service(
            prom_client=prom_client,
            composite_return=[
                self._bucket("MH-gemma-32b", "hash-gemma-v1", "/api/v1/chat", 100, 90),
            ],
        )
        svc._service_repo = MagicMock()
        svc._service_repo.get_names_and_models_by_service_ids = AsyncMock(
            return_value={"MH-gemma-32b": ("Mahavistaar Gemma 32B", "hash-gemma-v1", "gemma-3-27b-it")}
        )
        svc._model_repo = MagicMock()
        svc._model_repo.get_model_names = AsyncMock(return_value={"hash-gemma-v1": "gemma-3-27b-it"})

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "MH-gemma-32b")
        assert row["requests"] == 100
        assert row["success_pct"] == 90.0
        assert row["model_id"] == "hash-gemma-v1"
        model_row = next(m for m in result["model_totals"] if m["model_id"] == "hash-gemma-v1")
        assert model_row["requests"] == 100

        # composite_all must request missing_bucket on model_id (see docstring).
        sources = os_client.composite_all.call_args.kwargs["sources"]
        model_source = next(s for s in sources if "model_id" in s)
        assert model_source["model_id"]["terms"]["missing_bucket"] is True

        # sub_aggs must be a NAMED aggs mapping ({"by_status": {...}}), not a
        # bare _status_filters_agg() definition — OpenSearch rejects the
        # unnamed form with a parsing_exception at query time (caught only by
        # a live-cluster check, not by mocked unit tests, so pin the shape
        # here explicitly).
        sub_aggs = os_client.composite_all.call_args.kwargs["sub_aggs"]
        assert set(sub_aggs.keys()) == {"by_status"}
        assert "filters" in sub_aggs["by_status"]

    async def test_missing_model_id_bucket_still_counts_toward_service_total(self):
        """A composite bucket with model_id=None (missing_bucket) — service_id
        resolved but model_id didn't — must still count toward that
        service's per-service total, not be dropped."""
        prom_client = _mock_prom_client(scalar_return=0.0)
        svc, _ = _make_os_service(
            prom_client=prom_client,
            composite_return=[
                self._bucket("svc-1", None, "/api/v1/nmt/inference", 5, 5),
            ],
        )
        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "svc-1")
        assert row["requests"] == 5

    async def test_native_units_still_queried_via_prometheus(self):
        prom_client = _mock_prom_client(scalar_return=0.0)
        svc, _ = _make_os_service(prom_client=prom_client, composite_return=[])
        await svc.model_breakdown(tenant=None, time_range="24h")
        assert prom_client.query.called


@pytest.mark.asyncio
class TestModelUsageGrowthPct:
    async def test_none_when_too_early_in_month(self):
        svc, _ = _make_os_service()
        with patch("app.services.metering_service_opensearch.datetime") as mock_dt:
            from datetime import datetime, timezone
            mock_dt.now.return_value = datetime(2026, 3, 1, 0, 0, 30, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert await svc.model_usage_growth_pct() is None

    async def test_none_when_no_previous_month_traffic(self):
        svc, os_client = _make_os_service()
        os_client.count = AsyncMock(side_effect=[10, 0])
        assert await svc.model_usage_growth_pct() is None

    async def test_computes_growth_pct(self):
        svc, os_client = _make_os_service()
        os_client.count = AsyncMock(side_effect=[150, 100])
        result = await svc.model_usage_growth_pct()
        assert result == 50.0

    async def test_query_failure_returns_none(self):
        svc, os_client = _make_os_service()
        os_client.count = AsyncMock(side_effect=RuntimeError("boom"))
        assert await svc.model_usage_growth_pct() is None
