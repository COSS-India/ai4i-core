"""app/services/notification_management/monitoring_evaluator.py

The PromQL per alert, parsing of Prometheus results (missing or non-finite
values are dropped: no data never counts as recovery), mapping of
Prometheus errors to SOURCE failure codes, and a tick that hands one BAND
item per (alert, service) to the shared pipeline.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ai4i_core.kafka import NotificationName, ThresholdUnit

from app.services.notification_management import monitoring_evaluator as ev


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _vector(*samples):
    return {
        "status": "success",
        "data": {"resultType": "vector", "result": [
            {"metric": {"service_id": sid}, "value": [0, value]} for sid, value in samples
        ]},
    }


def test_queries_follow_the_design():
    queries = ev.build_queries("5m", 20)
    promql, unit = queries[NotificationName.ERROR_RATE_5XX]
    assert unit is ThresholdUnit.PERCENT
    assert 'status_code=~"5.."' in promql and "[5m]" in promql and ">= 20" in promql
    promql, unit = queries[NotificationName.LATENCY_P95]
    assert unit is ThresholdUnit.SECONDS and promql.startswith("histogram_quantile(0.95")
    assert set(queries) == {
        NotificationName.ERROR_RATE_4XX, NotificationName.ERROR_RATE_5XX,
        NotificationName.LATENCY_P50, NotificationName.LATENCY_P95, NotificationName.LATENCY_P99,
    }


@pytest.mark.asyncio
async def test_query_parses_values_and_drops_non_finite(monkeypatch):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    async with _client(lambda req: httpx.Response(200, json=_vector(("a", "1.5"), ("b", "NaN"), ("c", "+Inf")))) as c:
        assert await ev._query(c, "q") == {"a": 1.5}


@pytest.mark.asyncio
@pytest.mark.parametrize("handler, code", [
    (lambda req: httpx.Response(500), "PROMETHEUS_BAD_RESPONSE"),
    (lambda req: httpx.Response(200, json={"status": "error"}), "PROMETHEUS_BAD_RESPONSE"),
])
async def test_bad_responses_map_to_source_codes(monkeypatch, handler, code):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    async with _client(handler) as c:
        with pytest.raises(ev._SourceError) as exc:
            await ev._query(c, "q")
    assert exc.value.code.value == code


@pytest.mark.asyncio
async def test_unreachable_prometheus(monkeypatch):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")

    def boom(request):
        raise httpx.ConnectError("refused")

    async with _client(boom) as c:
        with pytest.raises(ev._SourceError) as exc:
            await ev._query(c, "q")
    assert exc.value.code.value == "PROMETHEUS_UNREACHABLE"


@pytest.mark.asyncio
async def test_tick_evaluates_only_alerts_with_bands_and_recipients(monkeypatch):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    ready = SimpleNamespace(bands=(object(),), recipient_roles={"ADMIN": True}, any_role_enabled=lambda: True)
    no_recipients = SimpleNamespace(bands=(object(),), recipient_roles={}, any_role_enabled=lambda: False)
    rows = {NotificationName.ERROR_RATE_5XX.value: ready, NotificationName.LATENCY_P95.value: no_recipients}
    snapshot = SimpleNamespace(get=lambda name: rows.get(name.value))
    runtime = MagicMock()
    runtime.cache.read = AsyncMock(return_value=SimpleNamespace(settings=snapshot))
    runtime.failures.record = AsyncMock()
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock(return_value=["event-1"])
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    queried = []

    def handler(request):
        queried.append(request.url.params["query"])
        return httpx.Response(200, json=_vector(("svc-a", "6.25"), ("svc-b", "0.5")))

    async with _client(handler) as c:
        result = await ev.run_tick(c)

    assert result == ["event-1"]
    assert len(queried) == 1 and 'status_code=~"5.."' in queried[0]
    items = emit.await_args.args[0]
    assert [(i.name, i.subject, i.observed.value) for i in items] == [
        (NotificationName.ERROR_RATE_5XX, {"service_id": "svc-a"}, Decimal("6.25")),
        (NotificationName.ERROR_RATE_5XX, {"service_id": "svc-b"}, Decimal("0.5")),
    ]


@pytest.mark.asyncio
async def test_prometheus_failure_writes_a_throttled_source_row(monkeypatch):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    rows = {NotificationName.ERROR_RATE_4XX.value: SimpleNamespace(bands=(object(),), recipient_roles={"ADMIN": True}, any_role_enabled=lambda: True)}
    runtime = MagicMock()
    runtime.cache.read = AsyncMock(return_value=SimpleNamespace(settings=SimpleNamespace(get=lambda n: rows.get(n.value))))
    runtime.failures.record = AsyncMock()
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock()
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    async with _client(lambda req: httpx.Response(503)) as c:
        assert await ev.run_tick(c) == []

    emit.assert_not_awaited()
    stage, code = runtime.failures.record.await_args.args
    assert stage.value == "SOURCE" and code.value == "PROMETHEUS_BAD_RESPONSE"
    assert runtime.failures.record.await_args.kwargs["throttle_s"] == ev.SOURCE_FAILURE_THROTTLE_S


def test_details_follow_the_consumer_template_contract():
    from datetime import datetime, timezone

    context = SimpleNamespace(
        subject={"service_id": "svc-a"},
        observed=SimpleNamespace(value=Decimal("6.25"), unit=ThresholdUnit.PERCENT),
        band=SimpleNamespace(value=Decimal("5"), severity=SimpleNamespace(value="WARNING")),
        occurred_at=datetime(2026, 9, 28, 10, 15, tzinfo=timezone.utc),
    )
    assert ev._details(context) == ["5", "28 Sep 2026, 03:45 PM IST", "6.25"]


@pytest.mark.asyncio
async def test_settings_unavailable_writes_a_settings_row(monkeypatch):
    runtime = MagicMock()
    runtime.cache.read = AsyncMock(return_value=SimpleNamespace(settings=None, settings_error=RuntimeError("down")))
    runtime.failures.record = AsyncMock()
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)

    async with _client(lambda req: httpx.Response(200, json=_vector())) as c:
        assert await ev.run_tick(c) == []

    stage, code = runtime.failures.record.await_args.args
    assert stage.value == "SETTINGS" and code.value == "SETTINGS_UNAVAILABLE"


@pytest.mark.asyncio
async def test_source_rows_name_the_promql(monkeypatch):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    rows = {NotificationName.LATENCY_P99.value: SimpleNamespace(bands=(object(),), recipient_roles={"ADMIN": True}, any_role_enabled=lambda: True)}
    runtime = MagicMock()
    runtime.cache.read = AsyncMock(return_value=SimpleNamespace(settings=SimpleNamespace(get=lambda n: rows.get(n.value))))
    runtime.failures.record = AsyncMock()
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)

    async with _client(lambda req: httpx.Response(500)) as c:
        await ev.run_tick(c)

    assert runtime.failures.record.await_args.kwargs["message"].startswith("L-0.99: ")


def test_lock_expires_just_before_the_next_tick():
    assert ev.lock_ttl_ms(60) == 55000
    assert ev.lock_ttl_ms(20) == 15000
    assert ev.lock_ttl_ms(3) == 1000
