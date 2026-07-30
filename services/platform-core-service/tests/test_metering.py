"""Unit tests for metering — PromQL builder, Prometheus client, and service layer.

All external dependencies (Prometheus HTTP, auth DB, Redis) are mocked.
No running services required.
"""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Builder tests ─────────────────────────────────────────────────────────────

from app.utils.metering_promql_builder import (
    LLM_CHAT_ENDPOINT_REGEX,
    PROMETHEUS_API_PATH_LABEL,
    SERVICE_BREAKDOWN_CONFIG,
    WINDOW_STEP,
    apply_time_range,
    build_base_selectors,
    sum_over_window,
    sum_over_window_by,
)


class TestBuildBaseSelectors:
    def test_always_excludes_unknown_tenant(self):
        sel = build_base_selectors()
        assert 'tenant!="unknown"' in sel

    def test_inference_only_adds_endpoint_filter(self):
        sel = build_base_selectors(inference_only=True)
        assert f"{PROMETHEUS_API_PATH_LABEL}=~" in sel

    def test_no_inference_only(self):
        sel = build_base_selectors(inference_only=False)
        assert f"{PROMETHEUS_API_PATH_LABEL}=~" not in sel

    def test_tenant_filter_added(self):
        sel = build_base_selectors(tenant="42")
        assert 'tenant="42"' in sel

    def test_tenant_unknown_still_excluded_when_scoped(self):
        sel = build_base_selectors(tenant="42")
        assert 'tenant!="unknown"' in sel
        assert 'tenant="42"' in sel

    def test_service_id_filter(self):
        sel = build_base_selectors(service_id="svc-1")
        assert 'service_id="svc-1"' in sel

    def test_extra_labels(self):
        sel = build_base_selectors(extra=['status_code=~"2.."'])
        assert 'status_code=~"2.."' in sel

    def test_always_returns_braces(self):
        sel = build_base_selectors(inference_only=False)
        assert sel.startswith("{") and sel.endswith("}")

    def test_endpoint_regex_override(self):
        sel = build_base_selectors(inference_only=True, endpoint_regex=LLM_CHAT_ENDPOINT_REGEX)
        assert f'{PROMETHEUS_API_PATH_LABEL}=~"{LLM_CHAT_ENDPOINT_REGEX}"' in sel

    def test_endpoint_regex_ignored_when_not_inference_only(self):
        sel = build_base_selectors(inference_only=False, endpoint_regex=LLM_CHAT_ENDPOINT_REGEX)
        assert PROMETHEUS_API_PATH_LABEL not in sel


class TestSumOverWindow:
    def test_with_window_uses_increase(self):
        expr = sum_over_window("metric{}", "24h")
        assert "increase(metric{}[24h])" in expr
        assert "offset 24h" in expr

    def test_no_window_plain_sum(self):
        expr = sum_over_window("metric{}", None)
        assert expr == "sum(metric{})"

    def test_all_window_plain_sum(self):
        expr = sum_over_window("metric{}", "all")
        assert expr == "sum(metric{})"

    def test_7d_window(self):
        expr = sum_over_window("metric{}", "7d")
        assert "[7d]" in expr
        assert "offset 7d" in expr


class TestSumOverWindowBy:
    def test_with_window_groups_by_label(self):
        expr = sum_over_window_by("metric{}", "model", "24h")
        assert expr.startswith("sum by(model) (")
        assert "increase(metric{}[24h])" in expr
        assert "offset 24h" in expr

    def test_no_window_plain_sum_by(self):
        expr = sum_over_window_by("metric{}", "model", None)
        assert expr == "sum by(model) (metric{})"

    def test_all_window_plain_sum_by(self):
        expr = sum_over_window_by("metric{}", "model", "all")
        assert expr == "sum by(model) (metric{})"


class TestApplyTimeRange:
    def test_applies_increase(self):
        expr = apply_time_range("metric{}", "1h")
        assert expr == "increase(metric{}[1h])"

    def test_no_window_returns_raw(self):
        expr = apply_time_range("metric{}", None)
        assert expr == "metric{}"


class TestServiceBreakdownConfig:
    def test_asr_divide_by_60(self):
        assert SERVICE_BREAKDOWN_CONFIG["asr"]["divide_by_60"] is True
        assert SERVICE_BREAKDOWN_CONFIG["asr"]["native_unit_suffix"] == "min"

    def test_speaker_diarization_divide_by_60(self):
        assert SERVICE_BREAKDOWN_CONFIG["speaker_diarization"]["divide_by_60"] is True

    def test_audio_language_detection_divide_by_60(self):
        assert SERVICE_BREAKDOWN_CONFIG["audio_language_detection"]["divide_by_60"] is True

    def test_ocr_use_success_as_native(self):
        assert SERVICE_BREAKDOWN_CONFIG["ocr"]["use_success_as_native"] is True
        assert SERVICE_BREAKDOWN_CONFIG["ocr"]["native_metric"] is None
        assert SERVICE_BREAKDOWN_CONFIG["ocr"]["metering_unit"] == "Images processed"

    def test_llm_has_token_type_filter(self):
        assert 'token_type="total"' in SERVICE_BREAKDOWN_CONFIG["llm"]["native_extra_labels"]

    def test_pipeline_has_no_native_metric(self):
        assert SERVICE_BREAKDOWN_CONFIG["pipeline"]["native_metric"] is None

    def test_audio_language_detection_present(self):
        assert "audio_language_detection" in SERVICE_BREAKDOWN_CONFIG

    def test_window_step_values(self):
        assert WINDOW_STEP["1h"] == "10m"
        assert WINDOW_STEP["24h"] == "4h"
        assert WINDOW_STEP["7d"] == "1d"
        assert WINDOW_STEP["30d"] == "7d"


# ── PrometheusClient tests ────────────────────────────────────────────────────

from app.utils.prometheus_client import PrometheusClient


class TestSafeFloat:
    def test_normal_value(self):
        assert PrometheusClient._safe_float("3.14") == pytest.approx(3.14)

    def test_nan_returns_default(self):
        assert PrometheusClient._safe_float("NaN") == 0.0

    def test_inf_returns_default(self):
        assert PrometheusClient._safe_float("+Inf") == 0.0

    def test_neg_inf_returns_default(self):
        assert PrometheusClient._safe_float("-Inf") == 0.0

    def test_custom_default(self):
        assert PrometheusClient._safe_float("NaN", default=-1.0) == -1.0

    def test_invalid_string_returns_default(self):
        assert PrometheusClient._safe_float("bad") == 0.0

    def test_zero(self):
        assert PrometheusClient._safe_float("0") == 0.0

    def test_integer_string(self):
        assert PrometheusClient._safe_float("42") == 42.0


@pytest.mark.asyncio
class TestPrometheusClientQuery:
    def _make_client(self, response_data: dict):
        http = AsyncMock()
        resp = MagicMock()
        resp.json.return_value = response_data
        resp.raise_for_status = MagicMock()
        http.get = AsyncMock(return_value=resp)
        return PrometheusClient("http://prometheus:9090", http)

    async def test_query_returns_result_list(self):
        client = self._make_client({
            "data": {"result": [{"metric": {"tenant": "1"}, "value": [1234, "5.0"]}]}
        })
        result = await client.query("up")
        assert len(result) == 1
        assert result[0]["metric"]["tenant"] == "1"

    async def test_query_empty_result(self):
        client = self._make_client({"data": {"result": []}})
        result = await client.query("up")
        assert result == []

    async def test_scalar_returns_float(self):
        client = self._make_client({
            "data": {"result": [{"metric": {}, "value": [1234, "7.5"]}]}
        })
        val = await client.scalar("sum(metric)")
        assert val == pytest.approx(7.5)

    async def test_scalar_empty_returns_zero(self):
        client = self._make_client({"data": {"result": []}})
        val = await client.scalar("sum(metric)")
        assert val == 0.0

    async def test_query_range_returns_matrix(self):
        client = self._make_client({
            "data": {"result": [{"metric": {}, "values": [[1000, "1.5"], [1060, "2.0"]]}]}
        })
        with patch.object(client._client, "get", client._client.get):
            result = await client.query_range("sum(rate(m[1m]))", 900, 1100, "1m")
        assert len(result) == 1
        assert len(result[0]["values"]) == 2

    async def test_query_range_uses_correct_params(self):
        http = AsyncMock()
        resp = MagicMock()
        resp.json.return_value = {"data": {"result": []}}
        resp.raise_for_status = MagicMock()
        http.get = AsyncMock(return_value=resp)
        client = PrometheusClient("http://prometheus:9090", http)

        await client.query_range("my_query", start=1000.0, end=2000.0, step="5m")

        http.get.assert_called_once()
        _, kwargs = http.get.call_args
        params = kwargs.get("params", {})
        assert params["query"] == "my_query"
        assert params["start"] == 1000.0
        assert params["end"] == 2000.0
        assert params["step"] == "5m"


# ── MeteringService tests ─────────────────────────────────────────────────────

from app.services.metering_service import MeteringService


def _make_service(query_return=None, scalar_return=0.0, range_return=None, auth_db=None):
    client = MagicMock()
    client.query = AsyncMock(return_value=query_return or [])
    client.scalar = AsyncMock(return_value=scalar_return)
    client.query_range = AsyncMock(return_value=range_return or [])
    return MeteringService(client=client, auth_db=auth_db)


@pytest.mark.asyncio
class TestTenantCount:
    async def test_returns_none_when_no_auth_db(self):
        svc = _make_service()
        result = await svc.tenant_count()
        assert result["total_tenants"] is None
        assert result["new_tenants"] is None
        assert result["auth_db_available"] is False

    async def test_always_uses_7d_for_new_tenants(self):
        auth_db = AsyncMock()
        total_result = MagicMock()
        total_result.scalar.return_value = 50
        new_result = MagicMock()
        new_result.scalar.return_value = 3
        auth_db.execute = AsyncMock(side_effect=[total_result, new_result])

        svc = _make_service(auth_db=auth_db)
        result = await svc.tenant_count()

        assert result["total_tenants"] == 50
        assert result["new_tenants"] == 3
        assert result["auth_db_available"] is True

        calls = auth_db.execute.call_args_list
        # Second call (new tenants) must use 7 days, not a variable interval
        new_query_sql = str(calls[1][0][0])
        assert "7 days" in new_query_sql.lower()


@pytest.mark.asyncio
class TestServiceBreakdown:
    def _make_endpoint_result(self, endpoint: str, value: float):
        return [{"metric": {PROMETHEUS_API_PATH_LABEL: endpoint}, "value": [0, str(value)]}]

    async def test_asr_native_units_divided_by_60(self):
        client = MagicMock()

        async def fake_query(promql):
            if f"sum by({PROMETHEUS_API_PATH_LABEL})" in promql:
                return self._make_endpoint_result("/api/v1/asr/inference", 100)
            return []

        async def fake_scalar(promql):
            # native metric query for ASR
            if "asr_audio_seconds" in promql:
                return 3600.0  # 3600 seconds
            return 0.0

        client.query = AsyncMock(side_effect=fake_query)
        client.scalar = AsyncMock(side_effect=fake_scalar)
        svc = MeteringService(client=client)

        result = await svc.service_breakdown(tenant=None, time_range="24h")
        asr_row = next(s for s in result["services"] if s["service"] == "ASR")
        # 3600 seconds / 60 = 60 minutes
        assert asr_row["native_units"] == 60.0

    async def test_ocr_uses_success_count_as_native(self):
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql:
                return self._make_endpoint_result("/api/v1/ocr/inference", 250)
            if f"sum by({PROMETHEUS_API_PATH_LABEL})" in promql:
                return self._make_endpoint_result("/api/v1/ocr/inference", 300)
            return []

        client.query = AsyncMock(side_effect=fake_query)
        client.scalar = AsyncMock(return_value=0.0)
        svc = MeteringService(client=client)

        result = await svc.service_breakdown(tenant=None, time_range="24h")
        ocr_row = next(s for s in result["services"] if s["service"] == "OCR")
        # native_units should be the success count, not a histogram value
        assert ocr_row["native_units"] == 250

    async def test_native_units_zero_not_null_when_no_usage(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=[])
        client.scalar = AsyncMock(return_value=0.0)
        svc = MeteringService(client=client)

        result = await svc.service_breakdown(tenant=None, time_range="24h")

        for row in result["services"]:
            assert row["native_units"] is not None
            assert row["native_units"] >= 0

    async def test_tenant_unknown_excluded_from_selectors(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=[])
        client.scalar = AsyncMock(return_value=0.0)
        svc = MeteringService(client=client)

        await svc.service_breakdown(tenant=None, time_range="24h")

        for call in client.query.call_args_list:
            promql = call[0][0]
            assert 'tenant!="unknown"' in promql


@pytest.mark.asyncio
class TestModelBreakdown:
    def _row(self, service_id: str, value: float):
        return [{"metric": {"service_id": service_id}, "value": [0, str(value)]}]

    def _rows(self, pairs: dict):
        return [{"metric": {"service_id": s}, "value": [0, str(v)]} for s, v in pairs.items()]

    def _repo(self, mapping: dict):
        repo = MagicMock()
        repo.get_names_and_models_by_service_ids = AsyncMock(return_value=mapping)
        return repo

    async def test_groups_by_service_id_and_computes_success_pct(self):
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql:
                return self._row("MH-gemma-32b", 90)
            if "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return self._row("MH-gemma-32b", 12345)
            return self._row("MH-gemma-32b", 100)

        client.query = AsyncMock(side_effect=fake_query)
        repo = self._repo({"MH-gemma-32b": ("Mahavistaar Gemma 32B", "gemma-3-27b-it")})
        svc = MeteringService(client=client, service_repo=repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "MH-gemma-32b")
        assert row["requests"] == 100
        assert row["success_pct"] == 90.0
        assert row["native_units"] == 12345.0
        assert row["name"] == "Mahavistaar Gemma 32B"
        assert row["model_name"] == "gemma-3-27b-it"

    async def test_name_falls_back_to_service_id_when_unresolved(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("orphan-service", 10))
        # No repo at all — e.g. DB unavailable.
        svc = MeteringService(client=client)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "orphan-service")
        assert row["name"] == "orphan-service"
        assert row["model_name"] is None

    async def test_name_falls_back_when_service_id_missing_from_db(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("deleted-service", 10))
        repo = self._repo({})  # service_id not found (e.g. soft-deleted)
        svc = MeteringService(client=client, service_repo=repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "deleted-service")
        assert row["name"] == "deleted-service"
        assert row["model_name"] is None

    async def test_empty_service_id_dropped(self):
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql:
                return []
            if "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return []
            return self._rows({"": 5, "MH-gemma-32b": 10})

        client.query = AsyncMock(side_effect=fake_query)
        svc = MeteringService(client=client)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        service_ids = [s["service_id"] for s in result["services"]]
        assert "" not in service_ids
        assert "MH-gemma-32b" in service_ids

    async def test_zero_total_gives_zero_success_pct(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("MH-gemma-32b", 0))
        svc = MeteringService(client=client)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "MH-gemma-32b")
        assert row["success_pct"] == 0.0

    async def test_sorted_by_requests_descending(self):
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql or "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return []
            return self._rows({"small-service": 10, "big-service": 500})

        client.query = AsyncMock(side_effect=fake_query)
        svc = MeteringService(client=client)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        assert [s["service_id"] for s in result["services"]] == ["big-service", "small-service"]

    async def test_tenant_scoping_applied_to_all_selectors(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=[])
        svc = MeteringService(client=client)

        await svc.model_breakdown(tenant="42", time_range="24h")

        for call in client.query.call_args_list:
            promql = call[0][0]
            assert 'tenant="42"' in promql

    async def test_llm_only_endpoint_selector_used(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=[])
        svc = MeteringService(client=client)

        await svc.model_breakdown(tenant=None, time_range="24h")

        request_calls = [
            call[0][0] for call in client.query.call_args_list
            if "telemetry_obsv_requests_total" in call[0][0]
        ]
        assert len(request_calls) == 2  # total + success
        for promql in request_calls:
            assert LLM_CHAT_ENDPOINT_REGEX in promql
            assert "by(service_id)" in promql
            assert "by(model)" not in promql

    async def test_repo_not_queried_when_no_traffic(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=[])
        repo = self._repo({})
        svc = MeteringService(client=client, service_repo=repo)

        await svc.model_breakdown(tenant=None, time_range="24h")

        repo.get_names_and_models_by_service_ids.assert_not_called()


@pytest.mark.asyncio
class TestThroughput:
    async def test_peak_rps_uses_query_range(self):
        range_result = [{"metric": {}, "values": [
            [1000, "5.0"],
            [1060, "12.5"],
            [1120, "8.0"],
        ]}]
        svc = _make_service(scalar_return=3.0, range_return=range_result)

        result = await svc.throughput(
            inference_only=True, tenant=None, service_id=None, time_range="24h"
        )

        svc._client.query_range.assert_called_once()
        assert result["peak_rps"] == pytest.approx(12.5)
        assert result["peak_at"] is not None
        # ISO timestamp format
        assert "T" in result["peak_at"]
        assert result["peak_at"].endswith("Z")

    async def test_peak_at_none_when_range_empty(self):
        svc = _make_service(scalar_return=2.0, range_return=[])
        result = await svc.throughput(
            inference_only=True, tenant=None, service_id=None, time_range="24h"
        )
        assert result["peak_rps"] is None
        assert result["peak_at"] is None

    async def test_avg_rps_returned(self):
        svc = _make_service(scalar_return=7.42)
        result = await svc.throughput(
            inference_only=True, tenant=None, service_id=None, time_range="1h"
        )
        assert result["avg_rps"] == pytest.approx(7.42, rel=1e-3)


@pytest.mark.asyncio
class TestActiveTenantsExcludesUnknown:
    async def test_query_excludes_unknown_tenant(self):
        svc = _make_service(query_return=[])
        await svc.active_tenants("24h")

        call_args = svc._client.query.call_args[0][0]
        assert 'tenant!="unknown"' in call_args

    async def test_filters_deleted_tenants_when_db_available(self):
        """Tenants present in Prometheus but absent from the DB are excluded.

        This covers the post-DB-flush scenario where stale Prometheus series
        for deleted tenants would otherwise inflate 7d/30d active-tenant counts.
        """
        prom_rows = [
            {"metric": {"tenant": "1"}, "value": [0, "5"]},
            {"metric": {"tenant": "2"}, "value": [0, "3"]},  # deleted tenant
            {"metric": {"tenant": "3"}, "value": [0, "8"]},
        ]
        # DB has only tenants 1 and 3; tenant 2 was deleted
        auth_db = AsyncMock()
        db_result = MagicMock()
        db_result.all.return_value = [(1,), (3,)]
        auth_db.execute = AsyncMock(return_value=db_result)

        svc = _make_service(query_return=prom_rows, auth_db=auth_db)
        result = await svc.active_tenants("7d")

        assert result["count"] == 2
        returned_ids = {t["tenant"] for t in result["active_tenants"]}
        assert returned_ids == {"1", "3"}
        assert "2" not in returned_ids

    async def test_no_filter_when_db_unavailable(self):
        """Falls back to unfiltered Prometheus results when auth DB is absent."""
        prom_rows = [
            {"metric": {"tenant": "1"}, "value": [0, "5"]},
            {"metric": {"tenant": "99"}, "value": [0, "2"]},
        ]
        svc = _make_service(query_return=prom_rows)  # no auth_db
        result = await svc.active_tenants("7d")

        assert result["count"] == 2


class TestFormatCount:
    def test_millions(self):
        assert MeteringService._format_count(1_250_000) == "1.25M"

    def test_thousands(self):
        assert MeteringService._format_count(973_100) == "973.1K"

    def test_small(self):
        assert MeteringService._format_count(42) == "42"

    def test_exact_million(self):
        assert MeteringService._format_count(1_000_000) == "1M"

    def test_exact_thousand(self):
        assert MeteringService._format_count(1_000) == "1K"
