"""Service List "Availability" column: instance (host:port) extraction, the
bulk Prometheus `up` lookup (app/utils/service_availability.py), and route
wiring — computed only when "availability" is in `columns=` (GET /services)."""
from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.service_availability import extract_instance, get_instance_availability

_spec = importlib.util.spec_from_file_location("app.routes.service", "app/routes/service.py")
_route = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.service"] = _route
_spec.loader.exec_module(_route)
list_services = _route.list_services
ServiceListFilterParams = _route.ServiceListFilterParams
ServiceListSortParams = _route.ServiceListSortParams
settings = _route.settings

ADMIN, NON_ADMIN = "1", "50"

# What service_to_dict + the list's model join produce for one row — trimmed
# to the fields ServiceResponse requires plus `endpoint`.
_ITEM = {
    "serviceId": "svc-1",
    "name": "LLM Prod",
    "modelId": "model-1",
    "modelVersion": "1.0",
    "endpoint": "http://45.194.2.154:8080/v1/completions",
    "inferenceServerType": "triton",
    "sslVerify": True,
    "isPublished": True,
    "isTryItDefault": False,
    "publishedAt": None,
    "unpublishedAt": None,
    "tierIds": None,
    "tierNames": None,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
    "versionStatus": "ACTIVE",
}


def _req(ids):
    r = MagicMock()
    r.headers = {"X-Permission-IDS": ids}
    return r


def _mock_prom(query_result):
    client = MagicMock()
    client.query = AsyncMock(return_value=query_result)
    return client


async def _call(ids, columns, item, monkeypatch, prom_client=None):
    if prom_client is not None:
        monkeypatch.setattr(_route, "get_prometheus_client", lambda request: prom_client)
    svc = MagicMock()
    svc.list_services = AsyncMock(return_value=([dict(item)], 1))
    result = await list_services(
        request=_req(ids), response=MagicMock(headers={}), svc=svc, db=MagicMock(),
        filters=ServiceListFilterParams(), paging=ServiceListSortParams(), columns=columns,
    )
    return result.data.services[0].model_dump(exclude_unset=True)


class TestExtractInstance:
    def test_strips_scheme_and_path_keeps_port(self):
        assert extract_instance("http://45.194.2.154:8080/v1/completions") == "45.194.2.154:8080"

    def test_https(self):
        assert extract_instance("https://45.194.2.154:8443/v1/x") == "45.194.2.154:8443"

    def test_hostname_with_hyphens_and_dots(self):
        # Regression fixture: this hostname is exactly what broke the naive
        # re.escape() approach (see TestGetInstanceAvailability.test_promql_is_unescaped).
        assert extract_instance("https://20c1c345-mock.pstmn.io:443/v2/models/llm/infer") == (
            "20c1c345-mock.pstmn.io:443"
        )

    @pytest.mark.parametrize("endpoint", [None, "", "not a url", "45.194.2.154:8080/no-scheme"])
    def test_unparseable_or_missing_is_none(self, endpoint):
        # Notably: a bare "ip:port/path" with no "http(s)://" scheme does NOT
        # parse to a host:port — urlparse reads the IP itself as the scheme instead.
        assert extract_instance(endpoint) is None

    def test_no_explicit_port_is_none(self):
        # Nothing to match a scrape instance against without a port.
        assert extract_instance("https://45.194.2.154/v1/completions") is None


class TestGetInstanceAvailability:
    @pytest.mark.asyncio
    async def test_no_job_name_returns_empty_without_querying(self):
        client = _mock_prom([])
        assert await get_instance_availability(client, None, ["45.194.2.154:8080"]) == {}
        client.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_instances_returns_empty_without_querying(self):
        client = _mock_prom([])
        assert await get_instance_availability(client, "ace-h200-vllm", []) == {}
        client.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_matched_instance_is_online_unscraped_instance_is_unknown(self):
        # An instance with no series at all (this job never targets it — Triton
        # ASR/NMT/TTS, an external LLM endpoint, ...) is unknown, not offline.
        client = _mock_prom([
            {"metric": {"instance": "45.194.2.154:8080"}, "value": [0, "1"]},
        ])
        status = await get_instance_availability(
            client, "ace-h200-vllm", ["45.194.2.154:8080", "10.0.0.9:8080"]
        )
        assert status == {"45.194.2.154:8080": True, "10.0.0.9:8080": None}

    @pytest.mark.asyncio
    async def test_up_value_zero_is_offline(self):
        client = _mock_prom([
            {"metric": {"instance": "45.194.2.154:8081"}, "value": [0, "0"]},
        ])
        status = await get_instance_availability(client, "ace-h200-vllm", ["45.194.2.154:8081"])
        assert status == {"45.194.2.154:8081": False}

    @pytest.mark.asyncio
    async def test_sibling_port_on_same_ip_does_not_affect_this_instance(self):
        # Regression: a host can run several models on different ports. One
        # port being up (or not scraped at all) must not leak onto another
        # port's status just because they share an IP.
        client = _mock_prom([
            {"metric": {"instance": "45.194.2.154:8080"}, "value": [0, "1"]},
        ])
        status = await get_instance_availability(
            client, "ace-h200-vllm", ["45.194.2.154:8080", "45.194.2.154:8100"]
        )
        assert status == {"45.194.2.154:8080": True, "45.194.2.154:8100": None}

    @pytest.mark.asyncio
    async def test_query_failure_degrades_to_empty_not_raises(self):
        client = MagicMock()
        client.query = AsyncMock(side_effect=RuntimeError("Prometheus unreachable"))
        assert await get_instance_availability(client, "ace-h200-vllm", ["45.194.2.154:8080"]) == {}

    @pytest.mark.asyncio
    async def test_promql_is_unescaped(self):
        # Regression: re.escape() turns "-" into "\-", which Prometheus's RE2
        # rejects outside a character class, and a literal "\." would need
        # double-escaping to survive PromQL's own string-literal grammar
        # first — either one 400s the whole bulk query (one bad hostname
        # breaks every instance in the same request). Instances must appear
        # byte-for-byte, unescaped.
        client = _mock_prom([])
        await get_instance_availability(
            client, "ace-h200-vllm", ["45.194.2.154:8080", "20c1c345-mock.pstmn.io:443"]
        )
        promql = client.query.call_args.args[0]
        assert "45.194.2.154:8080" in promql
        assert "20c1c345-mock.pstmn.io:443" in promql
        assert "\\-" not in promql
        assert "\\." not in promql


class TestRouteAnnotatesAvailability:
    @pytest.mark.asyncio
    async def test_set_when_column_selected_and_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "prometheus_url", "http://prometheus:9090")
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", "ace-h200-vllm")
        prom = _mock_prom([{"metric": {"instance": "45.194.2.154:8080"}, "value": [0, "1"]}])
        row = await _call(ADMIN, "name,availability", _ITEM, monkeypatch, prom_client=prom)
        assert row["availability"] is True
        prom.query.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_for_non_admin_too(self, monkeypatch):
        # Regression: the computed boolean isn't sensitive (only the raw
        # endpoint used to derive it is), but _filter_service_fields strips
        # anything not in _NON_ADMIN_SERVICE_FIELDS — without "availability"
        # in that allow-list, a non-admin's own selected column was silently
        # dropped after the Prometheus query had already run.
        monkeypatch.setattr(settings, "prometheus_url", "http://prometheus:9090")
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", "ace-h200-vllm")
        prom = _mock_prom([{"metric": {"instance": "45.194.2.154:8080"}, "value": [0, "1"]}])
        row = await _call(NON_ADMIN, "name,availability", _ITEM, monkeypatch, prom_client=prom)
        assert row["availability"] is True
        prom.query.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_absent_when_column_not_selected(self, monkeypatch):
        monkeypatch.setattr(settings, "prometheus_url", "http://prometheus:9090")
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", "ace-h200-vllm")
        prom = _mock_prom([])
        row = await _call(ADMIN, "name", _ITEM, monkeypatch, prom_client=prom)
        assert "availability" not in row
        prom.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_absent_when_omitting_columns_entirely(self, monkeypatch):
        # Full-item mode ("Omit to return the full item.") never computes it —
        # only an explicit `columns=...,availability` does.
        monkeypatch.setattr(settings, "prometheus_url", "http://prometheus:9090")
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", "ace-h200-vllm")
        prom = _mock_prom([])
        row = await _call(ADMIN, None, _ITEM, monkeypatch, prom_client=prom)
        assert "availability" not in row
        prom.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_when_job_name_unset(self, monkeypatch):
        monkeypatch.setattr(settings, "prometheus_url", "http://prometheus:9090")
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", None)
        row = await _call(ADMIN, "name,availability", _ITEM, monkeypatch)
        assert row["availability"] is None

    @pytest.mark.asyncio
    async def test_null_when_prometheus_url_unset(self, monkeypatch):
        monkeypatch.setattr(settings, "prometheus_url", None)
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", "ace-h200-vllm")
        row = await _call(ADMIN, "name,availability", _ITEM, monkeypatch)
        assert row["availability"] is None

    @pytest.mark.asyncio
    async def test_null_when_endpoint_unparseable(self, monkeypatch):
        monkeypatch.setattr(settings, "prometheus_url", "http://prometheus:9090")
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", "ace-h200-vllm")
        prom = _mock_prom([])
        item = dict(_ITEM, endpoint=None)
        row = await _call(ADMIN, "name,availability", item, monkeypatch, prom_client=prom)
        assert row["availability"] is None
        prom.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_when_prometheus_query_fails(self, monkeypatch):
        monkeypatch.setattr(settings, "prometheus_url", "http://prometheus:9090")
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", "ace-h200-vllm")
        prom = MagicMock()
        prom.query = AsyncMock(side_effect=RuntimeError("Prometheus unreachable"))
        row = await _call(ADMIN, "name,availability", _ITEM, monkeypatch, prom_client=prom)
        assert row["availability"] is None

    @pytest.mark.asyncio
    async def test_null_not_false_when_instance_is_not_scraped_by_this_job(self, monkeypatch):
        # Regression: a service whose instance this job never targets (e.g.
        # Triton ASR/NMT/TTS, or a sibling port on the same host that isn't
        # scraped) must not be reported as offline just because the vLLM
        # job's query came back empty for it — it's unknown (null), not false.
        monkeypatch.setattr(settings, "prometheus_url", "http://prometheus:9090")
        monkeypatch.setattr(settings, "prometheus_vllm_job_name", "ace-h200-vllm")
        prom = _mock_prom([])  # no series for this instance at all
        row = await _call(ADMIN, "name,availability", _ITEM, monkeypatch, prom_client=prom)
        assert row["availability"] is None
