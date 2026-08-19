"""Unit tests for metering — PromQL builder, Prometheus client, and service layer.

All external dependencies (Prometheus HTTP, auth DB, Redis) are mocked.
No running services required.
"""
from __future__ import annotations

import asyncio
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
    escape_label_value,
    sum_over_window,
    sum_over_window_by,
)


class TestEscapeLabelValue:
    def test_plain_value_unchanged(self):
        assert escape_label_value("Acme Corp") == "Acme Corp"

    def test_double_quote_escaped(self):
        assert escape_label_value('Acme "Corp"') == 'Acme \\"Corp\\"'

    def test_backslash_escaped(self):
        assert escape_label_value("Acme\\Corp") == "Acme\\\\Corp"

    def test_backslash_escaped_before_quote_so_result_is_not_double_escaped(self):
        # Backslashes must be escaped FIRST. If quotes were escaped first, the
        # backslash pass would then double the backslash the quote-escape just
        # inserted too, over-escaping the value a PromQL parser would receive.
        raw = "a" + "\\" + '"' + "b"  # 4 literal chars: a \ " b
        escaped = escape_label_value(raw)
        # Backslash doubled first (a\\"b), then the quote escaped (a\\\"b):
        # one embedded quote, preceded by exactly 3 backslash characters.
        expected = "a" + ("\\" * 3) + '"' + "b"
        assert escaped == expected

    def test_empty_string_unchanged(self):
        assert escape_label_value("") == ""


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
    def test_asr_native_metric_is_minutes(self):
        # The ASR histogram now reports audio minutes directly (inference_types.yaml
        # unit: audio_minutes) — no seconds->minutes division needed anymore.
        assert SERVICE_BREAKDOWN_CONFIG["asr"]["native_metric"] == (
            "telemetry_obsv_asr_audio_minutes_processed_sum"
        )
        assert SERVICE_BREAKDOWN_CONFIG["asr"]["round_2dp"] is True
        assert SERVICE_BREAKDOWN_CONFIG["asr"]["native_unit_suffix"] == "min"

    def test_speaker_diarization_native_metric_is_minutes(self):
        assert SERVICE_BREAKDOWN_CONFIG["speaker_diarization"]["native_metric"] == (
            "telemetry_obsv_speaker_diarization_minutes_processed_sum"
        )
        assert SERVICE_BREAKDOWN_CONFIG["speaker_diarization"]["round_2dp"] is True

    def test_audio_language_detection_native_metric_is_minutes(self):
        assert SERVICE_BREAKDOWN_CONFIG["audio_language_detection"]["native_metric"] == (
            "telemetry_obsv_audio_lang_detection_minutes_processed_sum"
        )
        assert SERVICE_BREAKDOWN_CONFIG["audio_language_detection"]["round_2dp"] is True

    def test_ocr_native_metric_is_image_count(self):
        # OCR bills by image count (inference_types.yaml unit: images). The
        # native metric is the histogram that now carries that exact billed
        # count (track_ocr_characters(characters=billed_input)), so the
        # dashboard equals billing even when a request carries >1 image —
        # request-success count would under-count in that case.
        assert SERVICE_BREAKDOWN_CONFIG["ocr"]["native_metric"] == (
            "telemetry_obsv_ocr_images_processed_sum"
        )
        assert SERVICE_BREAKDOWN_CONFIG["ocr"]["metering_unit"] == "Images processed"
        assert SERVICE_BREAKDOWN_CONFIG["ocr"]["native_unit_suffix"] == "images"
        assert "use_success_as_native" not in SERVICE_BREAKDOWN_CONFIG["ocr"]

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

    async def test_asr_native_units_reported_in_minutes(self):
        client = MagicMock()

        async def fake_query(promql):
            if f"sum by({PROMETHEUS_API_PATH_LABEL})" in promql:
                return self._make_endpoint_result("/api/v1/asr/inference", 100)
            return []

        async def fake_scalar(promql):
            # native metric query for ASR — histogram already reports minutes
            if "asr_audio_minutes" in promql:
                return 60.5
            return 0.0

        client.query = AsyncMock(side_effect=fake_query)
        client.scalar = AsyncMock(side_effect=fake_scalar)
        svc = MeteringService(client=client)

        result = await svc.service_breakdown(tenant=None, time_range="24h")
        asr_row = next(s for s in result["services"] if s["service"] == "ASR")
        # No division — the histogram's unit is already minutes; 2dp precision preserved.
        assert asr_row["native_units"] == 60.5

    async def test_ocr_native_units_from_image_count_histogram(self):
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql:
                return self._make_endpoint_result("/api/v1/ocr/inference", 250)
            if f"sum by({PROMETHEUS_API_PATH_LABEL})" in promql:
                return self._make_endpoint_result("/api/v1/ocr/inference", 300)
            return []

        async def fake_scalar(promql):
            # OCR's native metric now carries the billed image count.
            if "telemetry_obsv_ocr_images_processed_sum" in promql:
                return 512.0
            return 0.0

        client.query = AsyncMock(side_effect=fake_query)
        client.scalar = AsyncMock(side_effect=fake_scalar)
        svc = MeteringService(client=client)

        result = await svc.service_breakdown(tenant=None, time_range="24h")
        ocr_row = next(s for s in result["services"] if s["service"] == "OCR")
        # native_units is the billed image count (histogram sum), NOT the
        # request-success count — the two differ when a request has >1 image.
        assert ocr_row["native_units"] == 512
        assert ocr_row["native_unit_suffix"] == "images"

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
    def _row(self, service_id: str, value: float, model_id: str = ""):
        return [{"metric": {"service_id": service_id, "model_id": model_id}, "value": [0, str(value)]}]

    def _rows(self, pairs: dict, model_ids: dict = None):
        """pairs: {service_id: value}. model_ids: optional {service_id: model_id},
        defaulting to "" (no Prometheus label — e.g. a pre-upgrade series)."""
        model_ids = model_ids or {}
        return [
            {"metric": {"service_id": s, "model_id": model_ids.get(s, "")}, "value": [0, str(v)]}
            for s, v in pairs.items()
        ]

    def _repo(self, mapping: dict):
        repo = MagicMock()
        repo.get_names_and_models_by_service_ids = AsyncMock(return_value=mapping)
        return repo

    def _model_repo(self, mapping: dict):
        repo = MagicMock()
        repo.get_model_names = AsyncMock(return_value=mapping)
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
        repo = self._repo({"MH-gemma-32b": ("Mahavistaar Gemma 32B", "hash-gemma-v1", "gemma-3-27b-it")})
        svc = MeteringService(client=client, service_repo=repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "MH-gemma-32b")
        assert row["requests"] == 100
        assert row["success_pct"] == 90.0
        assert row["native_units"] == 12345.0
        assert row["name"] == "Mahavistaar Gemma 32B"
        assert row["model_id"] == "hash-gemma-v1"
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

    async def test_service_dropped_when_missing_from_registry(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("deleted-service", 10))
        repo = self._repo({})  # service_id not found (e.g. soft-deleted/renamed away)
        svc = MeteringService(client=client, service_repo=repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        service_ids = [s["service_id"] for s in result["services"]]
        assert "deleted-service" not in service_ids

    async def test_ghost_dropped_alongside_live_service_unaffected(self):
        # Mixed Prometheus result: one still-registered service plus one
        # ghost id in the same window — pins that the filter only removes
        # the ghost and leaves the live service's own numbers untouched.
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql:
                return self._rows({"live-service": 90, "deleted-service": 40})
            if "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return self._rows({"live-service": 12345, "deleted-service": 999})
            return self._rows({"live-service": 100, "deleted-service": 50})

        client.query = AsyncMock(side_effect=fake_query)
        repo = self._repo({"live-service": ("Live Service", "hash-gemma-v1", "gemma-3-27b-it")})
        svc = MeteringService(client=client, service_repo=repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        service_ids = [s["service_id"] for s in result["services"]]
        assert "deleted-service" not in service_ids
        assert service_ids == ["live-service"]

        row = result["services"][0]
        assert row["requests"] == 100
        assert row["success_pct"] == 90.0
        assert row["native_units"] == 12345.0
        assert row["name"] == "Live Service"
        assert row["model_id"] == "hash-gemma-v1"
        assert row["model_name"] == "gemma-3-27b-it"

    async def test_name_falls_back_to_service_id_when_registry_lookup_fails(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("orphan-service", 10))
        repo = self._repo({})
        repo.get_names_and_models_by_service_ids = AsyncMock(side_effect=RuntimeError("db down"))
        svc = MeteringService(client=client, service_repo=repo)

        # Registry lookup errored out — can't tell deleted from unreachable,
        # so don't hide the row, just show the raw id as before.
        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "orphan-service")
        assert row["name"] == "orphan-service"
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

    async def test_tenant_with_quote_is_escaped_in_tokens_selector(self):
        """The tokens_sel selector (unlike base_sel/success_sel, which go
        through build_base_selectors) is hand-built with an f-string — it was
        the one selector left unescaped before escape_label_value was added
        there too."""
        client = MagicMock()
        client.query = AsyncMock(return_value=[])
        svc = MeteringService(client=client)

        tenant = 'Acme "Corp"'
        await svc.model_breakdown(tenant=tenant, time_range="24h")

        tokens_calls = [
            call[0][0] for call in client.query.call_args_list
            if "telemetry_obsv_llm_tokens_processed_sum" in call[0][0]
        ]
        assert len(tokens_calls) == 1
        assert f'tenant="{escape_label_value(tenant)}"' in tokens_calls[0]
        assert f'tenant="{tenant}"' not in tokens_calls[0]

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
            assert "by(service_id, model_id)" in promql
            assert "by(model)" not in promql

    async def test_repo_not_queried_when_no_traffic(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=[])
        repo = self._repo({})
        model_repo = self._model_repo({})
        svc = MeteringService(client=client, service_repo=repo, model_repo=model_repo)

        await svc.model_breakdown(tenant=None, time_range="24h")

        repo.get_names_and_models_by_service_ids.assert_not_called()
        model_repo.get_model_names.assert_not_called()

    # ── model_totals: grouped/validated by model_id, from the Prometheus
    # label directly — see the ROLLOUT NOTEs on model_breakdown() ──────────

    async def test_model_totals_uses_prometheus_model_id(self):
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql:
                return self._row("svc-1", 90, model_id="hash-gemma-v1")
            if "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return self._row("svc-1", 12345, model_id="hash-gemma-v1")
            return self._row("svc-1", 100, model_id="hash-gemma-v1")

        client.query = AsyncMock(side_effect=fake_query)
        model_repo = self._model_repo({"hash-gemma-v1": "Gemma 3 27B"})
        svc = MeteringService(client=client, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        assert len(result["model_totals"]) == 1
        m = result["model_totals"][0]
        assert m["model_id"] == "hash-gemma-v1"
        assert m["model_name"] == "Gemma 3 27B"
        assert m["requests"] == 100
        assert m["success_pct"] == 90.0
        assert m["native_units"] == 12345.0

    async def test_model_totals_sums_multiple_services_under_one_model(self):
        """Two DIFFERENT services backed by the same model_id must collapse
        into ONE model_totals entry summing both — this is the actual
        grouping-by-model_id the tab now asked for, done at the PromQL layer
        via `by (service_id, model_id)`, not by re-aggregating `services`."""
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql:
                return []
            if "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return []
            return self._rows(
                {"svc-a": 300, "svc-b": 100},
                model_ids={"svc-a": "hash-gemma-v1", "svc-b": "hash-gemma-v1"},
            )

        client.query = AsyncMock(side_effect=fake_query)
        model_repo = self._model_repo({"hash-gemma-v1": "Gemma 3 27B"})
        svc = MeteringService(client=client, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        assert len(result["model_totals"]) == 1
        assert result["model_totals"][0]["requests"] == 400

    async def test_model_totals_excludes_model_with_no_registry_row(self):
        """A model_id with no mm_models row at all (hard-deleted, or a
        stale/never-existent id) is excluded. Contrast with
        test_model_totals_keeps_deprecated_model below: a DEPRECATED-but-
        present model must NOT be excluded the same way."""
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("svc-1", 10, model_id="hash-old-model"))
        model_repo = self._model_repo({})  # no row at all for this model_id
        svc = MeteringService(client=client, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        assert result["model_totals"] == []

    async def test_model_totals_keeps_deprecated_model(self):
        """A DEPRECATED model version still has a row in mm_models and can
        still be serving live traffic — deprecating is the normal step
        before activating a replacement version (see ModelRepository.
        get_model_names) — so it must not be treated as a ghost the way a
        hard-deleted model_id is."""
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("svc-1", 10, model_id="hash-deprecated-v1"))
        model_repo = self._model_repo({"hash-deprecated-v1": "Old Gemma"})
        svc = MeteringService(client=client, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        assert len(result["model_totals"]) == 1
        assert result["model_totals"][0]["model_id"] == "hash-deprecated-v1"
        assert result["model_totals"][0]["model_name"] == "Old Gemma"

    async def test_model_totals_skipped_when_registry_lookup_unavailable(self):
        """No model_repo at all (e.g. DB unavailable) — can't validate, so
        nothing is dropped rather than zeroing out every model."""
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("svc-1", 10, model_id="hash-gemma-v1"))
        svc = MeteringService(client=client)  # no model_repo

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        assert result["model_totals"][0]["model_id"] == "hash-gemma-v1"
        assert result["model_totals"][0]["model_name"] == "hash-gemma-v1"  # falls back to raw id

    async def test_model_totals_excludes_empty_model_id_bucket(self):
        """Rows with no model_id label at all (pre-upgrade series, or a
        resolution failure) must never form their own model_totals entry
        keyed by the empty string."""
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("svc-1", 10))  # model_id="" (default)
        model_repo = self._model_repo({})
        svc = MeteringService(client=client, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        assert result["model_totals"] == []
        model_repo.get_model_names.assert_not_called()

    async def test_model_totals_falls_back_to_db_when_prometheus_model_id_empty(self):
        """Regression: a service whose Prometheus series predate the
        model_id label (or whose traffic was recorded before that
        service's inference-service instance picked up ai4i-core 1.0.18+)
        still resolves fine in `services` via the DB join (svc_info) — the
        model-level view must apply the SAME fallback per-row, or this
        traffic silently vanishes from model_totals/top_models/
        active_models while still showing up in the per-service breakdown.
        Reported as: the Model Consumption chart shows only one model at
        100%, while the per-service drill-down table lists several."""
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("legacy-svc", 14))  # model_id="" from Prometheus
        repo = self._repo({"legacy-svc": ("Legacy Svc", "hash-legacy-v1", "test-llm-aug6-3")})
        model_repo = self._model_repo({"hash-legacy-v1": "test-llm-aug6-3"})
        svc = MeteringService(client=client, service_repo=repo, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")

        assert len(result["model_totals"]) == 1
        assert result["model_totals"][0]["model_id"] == "hash-legacy-v1"
        assert result["model_totals"][0]["model_name"] == "test-llm-aug6-3"
        assert result["model_totals"][0]["requests"] == 14

    async def test_effective_model_id_resolved_per_service_not_per_row(self):
        """A single service_id whose rows are inconsistently labeled across
        the 3 queries (e.g. the success-count row was scraped before the
        model_id label existed, but the total/tokens rows for the SAME
        service already carry it) must resolve to ONE model_id for every
        one of that service's rows — matching prom_model_id's per-service
        resolution, the same one `services` already uses at the
        prom_model_id.get(service_id) or db_model_id line. Resolving per
        ROW instead would split this service's success count off into a
        separate (wrongly excluded) empty-model_id bucket, understating
        the model's success_pct instead of just being consistently whole."""
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql:
                return self._row("svc-1", 9)  # no model_id label on this row
            if "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return self._row("svc-1", 900, model_id="hash-gemma-v1")
            return self._row("svc-1", 10, model_id="hash-gemma-v1")

        client.query = AsyncMock(side_effect=fake_query)
        repo = self._repo({"svc-1": ("Svc 1", "hash-gemma-v1", "Gemma 3 27B")})
        model_repo = self._model_repo({"hash-gemma-v1": "Gemma 3 27B"})
        svc = MeteringService(client=client, service_repo=repo, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")

        assert len(result["model_totals"]) == 1
        m = result["model_totals"][0]
        assert m["model_id"] == "hash-gemma-v1"
        assert m["requests"] == 10
        assert m["native_units"] == 900.0
        assert m["success_pct"] == 90.0  # 9/10 — the unlabeled row still attributed correctly

    async def test_model_totals_sums_prometheus_and_db_fallback_rows_together(self):
        """One service already carries the Prometheus model_id label,
        another (same model) doesn't yet — both must collapse into the
        SAME model_totals entry, matching what the per-service view already
        does for its own service_id-level fallback."""
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql or "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return []
            return self._rows(
                {"new-svc": 900, "legacy-svc": 11},
                model_ids={"new-svc": "hash-shared-v1"},  # legacy-svc defaults to "" (not in dict)
            )

        client.query = AsyncMock(side_effect=fake_query)
        repo = self._repo({
            "new-svc": ("New Svc", "hash-shared-v1", "test-llm-aug6-3"),
            "legacy-svc": ("Legacy Svc", "hash-shared-v1", "test-llm-aug6-3"),
        })
        model_repo = self._model_repo({"hash-shared-v1": "test-llm-aug6-3"})
        svc = MeteringService(client=client, service_repo=repo, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")

        assert len(result["model_totals"]) == 1
        assert result["model_totals"][0]["requests"] == 911

    async def test_deleted_service_traffic_still_counts_toward_active_model_total(self):
        """THE key behavioral change: a service can be dropped from the
        per-service `services` breakdown (ghost — deleted from mm_services)
        while its traffic still counts toward its model's total, as long as
        the model itself still has a Registry row — model-level totals are
        collapsed directly from Prometheus by model_id, independent of
        per-service existence filtering. See model_breakdown()'s second
        ROLLOUT NOTE."""
        client = MagicMock()

        async def fake_query(promql):
            if 'status_code=~"2.."' in promql or "telemetry_obsv_llm_tokens_processed_sum" in promql:
                return []
            return self._rows(
                {"live-svc": 100, "deleted-svc": 50},
                model_ids={"live-svc": "hash-gemma-v1", "deleted-svc": "hash-gemma-v1"},
            )

        client.query = AsyncMock(side_effect=fake_query)
        # Service registry only knows about live-svc — deleted-svc is a ghost.
        repo = self._repo({"live-svc": ("Live Svc", "hash-gemma-v1", "Gemma 3 27B")})
        model_repo = self._model_repo({"hash-gemma-v1": "Gemma 3 27B"})
        svc = MeteringService(client=client, service_repo=repo, model_repo=model_repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")

        service_ids = [s["service_id"] for s in result["services"]]
        assert "deleted-svc" not in service_ids
        assert "live-svc" in service_ids

        # The model's total is 150 (100 + 50) even though the flat
        # per-service breakdown only shows live-svc's 100.
        assert len(result["model_totals"]) == 1
        assert result["model_totals"][0]["requests"] == 150

    async def test_service_row_model_id_falls_back_to_db_when_prometheus_empty(self):
        """A legacy pre-upgrade series (no model_id label yet) still gets a
        model_id on its per-service row via the DB join fallback."""
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("svc-1", 10))  # model_id="" from Prometheus
        repo = self._repo({"svc-1": ("Svc 1", "hash-gemma-v1", "Gemma 3 27B")})
        svc = MeteringService(client=client, service_repo=repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "svc-1")
        assert row["model_id"] == "hash-gemma-v1"

    async def test_service_row_model_id_prefers_prometheus_over_db(self):
        client = MagicMock()
        client.query = AsyncMock(return_value=self._row("svc-1", 10, model_id="hash-from-prometheus"))
        repo = self._repo({"svc-1": ("Svc 1", "hash-from-db", "Gemma 3 27B")})
        svc = MeteringService(client=client, service_repo=repo)

        result = await svc.model_breakdown(tenant=None, time_range="24h")
        row = next(s for s in result["services"] if s["service_id"] == "svc-1")
        assert row["model_id"] == "hash-from-prometheus"


@pytest.mark.asyncio
class TestRegistryModelCount:
    async def test_no_model_repo_returns_none(self):
        svc = MeteringService(client=MagicMock())
        assert await svc.registry_model_count() is None

    async def test_delegates_to_model_repo_count_distinct_models(self):
        repo = MagicMock()
        repo.count_distinct_models = AsyncMock(return_value=42)
        svc = MeteringService(client=MagicMock(), model_repo=repo)

        assert await svc.registry_model_count() == 42
        repo.count_distinct_models.assert_awaited_once_with()

    async def test_db_failure_returns_none_not_raises(self):
        repo = MagicMock()
        repo.count_distinct_models = AsyncMock(side_effect=RuntimeError("db down"))
        svc = MeteringService(client=MagicMock(), model_repo=repo)

        assert await svc.registry_model_count() is None


class TestModelConsumptionRanking:
    """AI4IDS-2790 — ranks `model_breakdown`'s already-grouped `model_totals`
    (one row per model_id, grouping now happens at the Prometheus query layer
    via `by (service_id, model_id)` — see TestModelBreakdown for that)."""

    def _model_row(self, model_id, model_name, requests, success_pct=100.0):
        return {
            "model_id": model_id,
            "model_name": model_name,
            "requests": requests,
            "native_units": 0.0,
            "success_pct": success_pct,
        }

    def test_no_traffic_returns_empty(self):
        model_totals = [self._model_row("id-gemma", "gemma", 0)]
        most_used, ranked, grand_total = MeteringService.model_consumption_ranking(model_totals, limit=10)
        assert most_used is None
        assert ranked == []
        assert grand_total == 0

    def test_ranks_by_requests_descending(self):
        model_totals = [
            self._model_row("id-gemma", "gemma", 300),
            self._model_row("id-llama", "llama", 100),
        ]
        most_used, ranked, grand_total = MeteringService.model_consumption_ranking(model_totals, limit=10)

        assert most_used == {
            "model_id": "id-gemma", "model_name": "gemma", "requests": 300, "consumption_pct": 75.0,
        }
        assert grand_total == 400
        assert [m["model_name"] for m in ranked] == ["gemma", "llama"]
        assert ranked[0]["rank"] == 1
        assert ranked[0]["consumption_pct"] == 75.0
        assert ranked[1]["consumption_pct"] == 25.0
        assert ranked[0]["formatted_requests"] == "300"

    def test_most_used_always_agrees_with_top_ranked_model(self):
        model_totals = [
            self._model_row("id-A", "A", 400),
            self._model_row("id-B", "B", 250),
        ]
        most_used, ranked, _ = MeteringService.model_consumption_ranking(model_totals, limit=10)

        assert most_used["model_id"] == "id-A"
        assert ranked[0]["model_id"] == "id-A"
        # consumption_pct values sum to ~100% across the full ranked list
        # (exact here; in general only within a couple hundredths of 100 due
        # to per-row 2dp rounding).
        assert round(sum(m["consumption_pct"] for m in ranked), 2) == 100.0

    def test_limit_caps_ranked_list(self):
        model_totals = [
            self._model_row(f"id-{i}", f"model-{i}", 10 * (i + 1))
            for i in range(5)
        ]
        _, ranked, _ = MeteringService.model_consumption_ranking(model_totals, limit=2)
        assert len(ranked) == 2
        assert [m["rank"] for m in ranked] == [1, 2]

    def test_zero_request_models_excluded_from_consumption_pct(self):
        model_totals = [
            self._model_row("id-gemma", "gemma", 100),
            self._model_row("id-unused", "unused-model", 0),
        ]
        _, ranked, _ = MeteringService.model_consumption_ranking(model_totals, limit=10)
        assert [m["model_name"] for m in ranked] == ["gemma"]
        assert ranked[0]["consumption_pct"] == 100.0


class TestModelConsumptionKpis:
    """AI4IDS-2790 — overall_success_rate_pct is REQUEST-WEIGHTED (matches the
    FE's existing fallback formula), not a plain average across services.
    `active_models` now just counts `model_totals` entries with traffic —
    model_breakdown() has already grouped/validated those by model_id."""

    def _row(self, service_id, name, model_name, requests, success_pct, model_id=None):
        return {
            "service_id": service_id,
            "name": name,
            "model_id": model_id,
            "model_name": model_name,
            "requests": requests,
            "native_units": 0.0,
            "success_pct": success_pct,
        }

    def _model_row(self, model_id, model_name, requests, success_pct=100.0):
        return {
            "model_id": model_id,
            "model_name": model_name,
            "requests": requests,
            "native_units": 0.0,
            "success_pct": success_pct,
        }

    def test_request_weighted_not_plain_average(self):
        # Plain average would give (100+50)/2 = 75.0 — must NOT be that.
        services = [
            self._row("s1", "Svc 1", "gemma", 900, 100.0),
            self._row("s2", "Svc 2", "llama", 100, 50.0),
        ]
        kpis = MeteringService.model_consumption_kpis(services, [])
        assert kpis["overall_success_rate_pct"] == 95.0

    def test_zero_request_services_excluded_from_average(self):
        services = [
            self._row("s1", "Svc 1", "gemma", 100, 80.0),
            self._row("s2", "Svc 2", "unused-model", 0, 0.0),
        ]
        kpis = MeteringService.model_consumption_kpis(services, [])
        assert kpis["overall_success_rate_pct"] == 80.0

    def test_no_traffic_gives_none_rate_but_zero_active_models(self):
        """0 is a real answer for active_models ("no models were active");
        only overall_success_rate_pct is genuinely undefined with no data."""
        services = [self._row("s1", "Svc 1", "gemma", 0, 0.0)]
        kpis = MeteringService.model_consumption_kpis(services, [])
        assert kpis["overall_success_rate_pct"] is None
        assert kpis["active_models"] == 0
        assert kpis["worst"] is None

    def test_active_models_counts_model_totals_with_traffic(self):
        """model_totals is already one row per Registry-validated model_id,
        each with a distinct name here — counting distinct names gives the
        same answer as counting rows in this case."""
        model_totals = [
            self._model_row("id-gemma", "gemma", 15),
            self._model_row("id-llama", "llama", 20),
            self._model_row("id-idle", "idle-model", 0),  # no traffic -> excluded
        ]
        kpis = MeteringService.model_consumption_kpis([], model_totals)
        assert kpis["active_models"] == 2

    def test_active_models_dedupes_multiple_active_versions_of_same_name(self):
        """Two concurrently-ACTIVE versions of the same model (distinct
        model_ids, e.g. a canary rollout) both receiving traffic must count
        as ONE active model, matching registry_model_count's name-based
        identity — otherwise active_models could exceed total_models."""
        model_totals = [
            self._model_row("id-gemma-v1", "Gemma", 15),
            self._model_row("id-gemma-v2", "gemma", 5),  # same name, different casing
            self._model_row("id-llama", "llama", 20),
        ]
        kpis = MeteringService.model_consumption_kpis([], model_totals)
        assert kpis["active_models"] == 2

    def test_worst_picks_highest_failure_rate_among_active_services(self):
        services = [
            self._row("s1", "Svc 1", "gemma", 100, 90.0),   # 10% failure
            self._row("s2", "Svc 2", "llama", 50, 60.0),    # 40% failure — worst
            self._row("s3", "Svc 3", "idle-model", 0, 0.0),  # no traffic -> excluded
        ]
        kpis = MeteringService.model_consumption_kpis(services, [])
        assert kpis["worst"]["service_id"] == "s2"


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

    async def test_valid_tenant_names_query_filters_by_active_status(self):
        """The DB lookup backing the active-tenants filter only returns
        ACTIVE-status organisations, so PENDING/SUSPENDED/DEACTIVATED
        tenants can't inflate the Active Tenants count."""
        auth_db = AsyncMock()
        db_result = MagicMock()
        db_result.all.return_value = []
        auth_db.execute = AsyncMock(return_value=db_result)

        svc = _make_service(query_return=[], auth_db=auth_db)
        await svc.active_tenants("24h")

        executed_sql = str(auth_db.execute.call_args[0][0])
        assert "status = 'ACTIVE'" in executed_sql

    async def test_excludes_pending_tenant_traffic(self):
        """A tenant whose status is PENDING (not yet ACTIVE) must not count
        as an active tenant, even if stale Prometheus series exist for it."""
        prom_rows = [
            {"metric": {"tenant": "acme"}, "value": [0, "5"]},  # ACTIVE
            {"metric": {"tenant": "pending-org"}, "value": [0, "3"]},  # PENDING
        ]
        # DB WHERE status='ACTIVE' would only ever return active orgs.
        auth_db = AsyncMock()
        db_result = MagicMock()
        db_result.all.return_value = [("acme",)]
        auth_db.execute = AsyncMock(return_value=db_result)

        svc = _make_service(query_return=prom_rows, auth_db=auth_db)
        result = await svc.active_tenants("24h")

        assert result["count"] == 1
        returned = {t["tenant"] for t in result["active_tenants"]}
        assert returned == {"acme"}
        assert "pending-org" not in returned

    async def test_valid_names_param_skips_auth_db_fetch(self):
        """Passing valid_names explicitly must not touch self._auth_db at
        all — this is what lets overview_tenant_data() share ONE fetch
        across several active_tenants() calls instead of each one racing to
        use the same AsyncSession concurrently (see its docstring)."""
        prom_rows = [
            {"metric": {"tenant": "acme"}, "value": [0, "5"]},
            {"metric": {"tenant": "ghost-org"}, "value": [0, "3"]},
        ]
        auth_db = AsyncMock()
        svc = _make_service(query_return=prom_rows, auth_db=auth_db)

        result = await svc.active_tenants("24h", valid_names={"acme"})

        auth_db.execute.assert_not_called()
        assert result["count"] == 1
        assert {t["tenant"] for t in result["active_tenants"]} == {"acme"}

    async def test_valid_names_none_means_unfiltered(self):
        """Explicitly passing None (e.g. the auth DB was unavailable when
        overview_tenant_data() pre-fetched it) must behave like the
        no-filter fallback, not like an empty allow-list."""
        prom_rows = [{"metric": {"tenant": "acme"}, "value": [0, "5"]}]
        svc = _make_service(query_return=prom_rows)

        result = await svc.active_tenants("24h", valid_names=None)
        assert result["count"] == 1


@pytest.mark.asyncio
class TestOverviewTenantData:
    """Regression coverage for the AsyncSession concurrency bug: gathering
    tenant_count() together with several active_tenants() calls (each
    independently hitting self._auth_db) intermittently raised
    sqlalchemy.exc.InvalidRequestError. overview_tenant_data() must run every
    auth-DB touch sequentially before firing the per-window Prometheus
    queries concurrently."""

    async def test_auth_db_touched_sequentially_not_concurrently(self):
        """tenant_count()'s 2 queries + the 1 valid-names fetch must all
        complete one at a time — never more than one in-flight execute()."""
        in_flight = 0
        max_concurrent = 0

        async def fake_execute(*args, **kwargs):
            nonlocal in_flight, max_concurrent
            in_flight += 1
            max_concurrent = max(max_concurrent, in_flight)
            await asyncio.sleep(0)  # yield, so a real race would surface
            in_flight -= 1
            result = MagicMock()
            result.scalar.return_value = 1
            result.all.return_value = []
            return result

        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(side_effect=fake_execute)
        svc = _make_service(query_return=[], auth_db=auth_db)

        await svc.overview_tenant_data(["24h", "7d", "30d"])

        assert max_concurrent == 1

    async def test_valid_names_fetched_once_and_shared_across_windows(self):
        prom_rows = [{"metric": {"tenant": "acme"}, "value": [0, "5"]}]
        auth_db = AsyncMock()
        total_result = MagicMock(scalar=lambda: 1)
        names_result = MagicMock()
        names_result.all.return_value = [("acme",)]
        # tenant_count() issues 2 execute()s, then the valid-names fetch is a 3rd.
        auth_db.execute = AsyncMock(side_effect=[total_result, total_result, names_result])
        svc = _make_service(query_return=prom_rows, auth_db=auth_db)

        tc, active_by_range = await svc.overview_tenant_data(["24h", "7d", "30d"])

        assert auth_db.execute.await_count == 3  # not 1 (tenant_count) + 3x1 (per window)
        assert set(active_by_range.keys()) == {"24h", "7d", "30d"}
        for window_result in active_by_range.values():
            assert window_result["count"] == 1

    async def test_returns_tenant_count_result(self):
        auth_db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = 7
        names_result = MagicMock()
        names_result.all.return_value = []
        auth_db.execute = AsyncMock(side_effect=[result, result, names_result])
        svc = _make_service(query_return=[], auth_db=auth_db)

        tc, _ = await svc.overview_tenant_data(["24h"])
        assert tc["total_tenants"] == 7
        assert tc["auth_db_available"] is True

    async def test_prometheus_failure_in_one_window_does_not_raise(self):
        """A failing Prometheus query in one window must come back as an
        Exception in the returned dict, not propagate out of this method —
        otherwise the caller (routes/metering.py) never reaches
        _partition_results and /overview 500s instead of degrading."""
        auth_db = AsyncMock()
        count_result = MagicMock(scalar=lambda: 1)
        names_result = MagicMock()
        names_result.all.return_value = []
        auth_db.execute = AsyncMock(side_effect=[count_result, count_result, names_result])

        client = MagicMock()
        client.query = AsyncMock(side_effect=RuntimeError("prometheus unreachable"))
        svc = MeteringService(client=client, auth_db=auth_db)

        tc, active_by_range = await svc.overview_tenant_data(["24h", "7d"])

        assert isinstance(active_by_range["24h"], RuntimeError)
        assert isinstance(active_by_range["7d"], RuntimeError)
        assert tc["auth_db_available"] is True


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
