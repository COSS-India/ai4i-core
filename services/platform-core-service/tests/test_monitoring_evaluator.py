"""app/services/notification_management/monitoring_evaluator.py

The PromQL per alert, parsing of Prometheus results (missing or non-finite
values are dropped: no data never counts as recovery), mapping of
Prometheus errors to SOURCE failure codes, a tick that hands one BAND
item per (alert, service) to the shared pipeline, and quiet services whose
open incident is past the cooldown handed in below every band so it resets
(only with no traffic at all: under the minimum keeps the incident).
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


def _row(row_id=1, *, roles=True, lowest="1"):
    return SimpleNamespace(
        id=row_id, bands=(SimpleNamespace(value=Decimal(lowest)),),
        recipient_roles={"ADMIN": True} if roles else {}, any_role_enabled=lambda: roles,
    )


def _sessions(rows=(), error=None):
    """core_session_factory whose session returns `rows` for the open
    incidents read (or raises `error`); .calls records the parameters."""
    calls = []

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, statement, params):
            calls.append(params)
            if error is not None:
                raise error
            return SimpleNamespace(mappings=lambda: iter(
                {"notification_id": r["notification_id"], "subject": {"service_id": r["service_id"]}} for r in rows
            ))

    factory = _Session
    factory.calls = calls
    return factory


def _runtime(rows_by_name, incidents=(), error=None):
    runtime = MagicMock()
    runtime.cache.read = AsyncMock(return_value=SimpleNamespace(
        settings=SimpleNamespace(get=lambda n: rows_by_name.get(n.value))
    ))
    runtime.failures.record = AsyncMock()
    runtime.core_session_factory = _sessions(incidents, error)
    runtime.config.notif_monitor_cooldown_s = 1800
    return runtime


def _is_count(promql):
    return promql == ev.request_count_query("5m")


@pytest.fixture(autouse=True)
def service_names(monkeypatch):
    """ServiceRepository stand-in: .names {service_id: name}, .error raised
    by every read, .calls the service_ids read."""
    state = SimpleNamespace(names={}, error=None, calls=[])

    class _Repository:
        def __init__(self, session):
            pass

        async def get_name_by_service_id(self, service_id):
            state.calls.append(service_id)
            if state.error is not None:
                raise state.error
            return state.names.get(service_id)

    monkeypatch.setattr(ev, "ServiceRepository", _Repository)
    return state


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
    rows = {NotificationName.ERROR_RATE_5XX.value: _row(), NotificationName.LATENCY_P95.value: _row(2, roles=False)}
    runtime = _runtime(rows)
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
    runtime = _runtime({NotificationName.ERROR_RATE_4XX.value: _row()})
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
    assert ev._details(context) == ["5", "28 Sep 2026, 03:45 PM IST", "6.25", "svc-a"]


@pytest.mark.asyncio
async def test_services_breaching_in_one_tick_merge_into_one_list(monkeypatch):
    """12:27 — asr, llm and tts all cross 5xx in one tick. Each item names its
    own service, and every item carries the merge that lists all three in
    one email, worst first."""
    from datetime import datetime, timezone

    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    runtime = _runtime({NotificationName.ERROR_RATE_5XX.value: _row()})
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock(return_value=["event-1", "event-2"])
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    vector = _vector(("asr-service", "9.1"), ("llm-service", "6.2"), ("tts-service", "11.3"))
    async with _client(lambda req: httpx.Response(200, json=vector)) as c:
        await ev.run_tick(c)

    bands = {"asr-service": "5", "llm-service": "5", "tts-service": "10"}
    when = datetime(2026, 9, 30, 6, 57, tzinfo=timezone.utc)
    items = emit.await_args.args[0]
    parts = [
        await item.details(SimpleNamespace(
            subject=item.subject, observed=item.observed, occurred_at=when,
            band=SimpleNamespace(value=Decimal(bands[item.subject["service_id"]])),
        ))
        for item in items
    ]
    assert [(p[2], p[3]) for p in parts] == [("9.1", "asr-service"), ("6.2", "llm-service"), ("11.3", "tts-service")]
    assert {item.group_details for item in items} == {ev._group_details}
    # No mm_services row in this test: each email shows the service_id.
    assert ev._group_details(parts) == [
        "5", "30 Sep 2026, 12:27 PM IST", "11.3", "tts-service",
        [["tts-service", "11.3", "10"], ["asr-service", "9.1", "5"], ["llm-service", "6.2", "5"]],
    ]


def _context(service_id, band="5", value="6.25"):
    from datetime import datetime, timezone
    return SimpleNamespace(
        subject={"service_id": service_id}, observed=SimpleNamespace(value=Decimal(value)),
        band=SimpleNamespace(value=Decimal(band)), occurred_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_emails_name_the_service_not_its_id(service_names):
    """de9a4570… fires: the email shows "indictrans-gpu-t4", read once per
    tick however many alerts fire for it."""
    service_names.names = {"de9a4570f8c14f6859cb79c1934a4db9": "indictrans-gpu-t4"}
    names = ev._ServiceNames(_runtime({}))

    first = await names.details(_context("de9a4570f8c14f6859cb79c1934a4db9"))
    second = await names.details(_context("de9a4570f8c14f6859cb79c1934a4db9", band="10", value="12"))

    assert first == ["5", "01 Oct 2026, 01:30 PM IST", "6.25", "indictrans-gpu-t4"]
    assert second[3] == "indictrans-gpu-t4"
    assert service_names.calls == ["de9a4570f8c14f6859cb79c1934a4db9"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [None, RuntimeError("db down")])
async def test_unknown_service_or_failed_lookup_shows_the_service_id(service_names, error):
    service_names.error = error

    details = await ev._ServiceNames(_runtime({})).details(_context("deepseek-r1-8b/sep23"))

    assert details[3] == "deepseek-r1-8b/sep23"


@pytest.mark.asyncio
async def test_merged_email_lists_service_names(monkeypatch, service_names):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    service_names.names = {"svc-a": "ASR Service", "svc-b": "TTS Service"}
    runtime = _runtime({NotificationName.ERROR_RATE_5XX.value: _row()})
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock(return_value=[])
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    async with _client(lambda req: httpx.Response(200, json=_vector(("svc-a", "9.1"), ("svc-b", "11.3")))) as c:
        await ev.run_tick(c)

    items = emit.await_args.args[0]
    parts = [await item.details(_context(item.subject["service_id"], value=str(item.observed.value))) for item in items]
    assert ev._group_details(parts)[3:] == ["TTS Service", [["TTS Service", "11.3", "5"], ["ASR Service", "9.1", "5"]]]
    assert [i.subject for i in items] == [{"service_id": "svc-a"}, {"service_id": "svc-b"}]


def test_merge_sorts_by_value_not_text():
    """"10.5" sorts before "9" as text; the list must still be worst first."""
    parts = [["5", "t", "9", "a"], ["5", "t", "10.5", "b"]]

    assert ev._group_details(parts)[4] == [["b", "10.5", "5"], ["a", "9", "5"]]
    assert ev._group_details(parts)[:4] == ["5", "t", "10.5", "b"]


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
    runtime = _runtime({NotificationName.LATENCY_P99.value: _row()})
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)

    async with _client(lambda req: httpx.Response(500)) as c:
        await ev.run_tick(c)

    assert runtime.failures.record.await_args.kwargs["message"].startswith("L-0.99: ")


@pytest.mark.asyncio
async def test_quiet_service_with_an_open_incident_is_handed_in_below_every_band(monkeypatch):
    """svc-old fired yesterday and has had no traffic since: missing from the
    result, its incident past the cooldown is handed in at 0 so the pipeline
    resets it. svc-a is in the result and is evaluated as usual, once."""
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    runtime = _runtime(
        {NotificationName.LATENCY_P99.value: _row(14)},
        incidents=[{"notification_id": 14, "service_id": "svc-old"}, {"notification_id": 14, "service_id": "svc-a"}],
    )
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock(return_value=[])
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    def handler(request):
        if _is_count(request.url.params["query"]):
            return httpx.Response(200, json=_vector(("svc-a", "25")))
        return httpx.Response(200, json=_vector(("svc-a", "0.9")))

    async with _client(handler) as c:
        await ev.run_tick(c)

    items = emit.await_args.args[0]
    assert [(i.subject["service_id"], i.observed.value, i.observed.unit) for i in items] == [
        ("svc-a", Decimal("0.9"), ThresholdUnit.SECONDS),
        ("svc-old", Decimal(0), ThresholdUnit.SECONDS),
    ]
    assert items[1].details is None
    assert runtime.core_session_factory.calls == [{"notification_ids": [14], "tenant_id": "PLATFORM", "cooldown_s": 1800}]


@pytest.mark.asyncio
@pytest.mark.parametrize("count_response", [
    httpx.Response(200, json=_vector(("svc-old", "7"))),   # traffic under the minimum
    httpx.Response(503),                                   # count unknown
])
async def test_low_traffic_or_unknown_count_keeps_the_incident(monkeypatch, count_response):
    """svc-old still has 7 requests (under 20), so it is not quiet: resetting
    it would email again once per cooldown while it stays bad. A failed
    count query resets nothing either. svc-a is still evaluated."""
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    runtime = _runtime(
        {NotificationName.LATENCY_P99.value: _row(14)},
        incidents=[{"notification_id": 14, "service_id": "svc-old"}],
    )
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock(return_value=[])
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    def handler(request):
        if _is_count(request.url.params["query"]):
            return count_response
        return httpx.Response(200, json=_vector(("svc-a", "0.9")))

    async with _client(handler) as c:
        await ev.run_tick(c)

    assert [i.subject["service_id"] for i in emit.await_args.args[0]] == ["svc-a"]


def test_request_count_query_has_no_minimum():
    promql = ev.request_count_query("5m")
    assert promql == 'sum by (service_id) (increase(telemetry_obsv_requests_total{service_id!=""}[5m]))'


@pytest.mark.asyncio
async def test_a_failed_query_resets_nothing(monkeypatch):
    """Missing data from a failed query is not quiet: the open incident stays."""
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    runtime = _runtime(
        {NotificationName.ERROR_RATE_5XX.value: _row(11)},
        incidents=[{"notification_id": 11, "service_id": "svc-old"}],
    )
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock()
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    async with _client(lambda req: httpx.Response(503)) as c:
        assert await ev.run_tick(c) == []

    emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_incidents_of_one_alert_do_not_reset_another(monkeypatch):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    runtime = _runtime(
        {NotificationName.ERROR_RATE_4XX.value: _row(10), NotificationName.ERROR_RATE_5XX.value: _row(11)},
        incidents=[{"notification_id": 10, "service_id": "svc-old"}],
    )
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock(return_value=[])
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    async with _client(lambda req: httpx.Response(200, json=_vector())) as c:
        await ev.run_tick(c)

    items = emit.await_args.args[0]
    assert [(i.name, i.subject["service_id"]) for i in items] == [(NotificationName.ERROR_RATE_4XX, "svc-old")]


@pytest.mark.asyncio
async def test_a_band_at_zero_skips_the_quiet_reset(monkeypatch):
    """0 would reach a band at 0 and fire, so quiet services are left alone."""
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    runtime = _runtime(
        {NotificationName.ERROR_RATE_4XX.value: _row(10, lowest="0")},
        incidents=[{"notification_id": 10, "service_id": "svc-old"}],
    )
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock()
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    async with _client(lambda req: httpx.Response(200, json=_vector())) as c:
        assert await ev.run_tick(c) == []

    emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_incident_read_failure_still_evaluates_the_results(monkeypatch):
    monkeypatch.setattr(ev.settings, "prometheus_url", "http://prom")
    runtime = _runtime({NotificationName.ERROR_RATE_5XX.value: _row(11)}, error=RuntimeError("db down"))
    monkeypatch.setattr(ev, "get_notification_runtime", lambda: runtime)
    emit = AsyncMock(return_value=["event-1"])
    monkeypatch.setattr(ev, "emit_band_batch", emit)

    async with _client(lambda req: httpx.Response(200, json=_vector(("svc-a", "12")))) as c:
        assert await ev.run_tick(c) == ["event-1"]

    assert [i.subject["service_id"] for i in emit.await_args.args[0]] == ["svc-a"]


def test_lock_expires_just_before_the_next_tick():
    assert ev.lock_ttl_ms(60) == 55000
    assert ev.lock_ttl_ms(20) == 15000
    assert ev.lock_ttl_ms(3) == 1000
