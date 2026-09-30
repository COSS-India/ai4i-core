"""emit_band_batch grouping (BandItem.group_details): items of one call with
the same name and tenant that fire together are sent as one event, each
still claiming its own ledger row; items without group_details are sent
one event each, as before."""

from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai4i_core.kafka import pipeline
from ai4i_core.kafka.cache import CacheRead
from ai4i_core.kafka.constants import (
    PLATFORM_TENANT_ID,
    NotificationModule,
    NotificationName,
    NotificationScope,
    NotificationType,
    Severity,
    ThresholdUnit,
)
from ai4i_core.kafka.keys import monitoring_subject, utc_now
from ai4i_core.kafka.models import NO_LEDGER_ROW, Band, LedgerState, Measurement, Recipient, SettingsRow, SettingsSnapshot
from ai4i_core.kafka.pipeline import BandItem, emit_band_batch

WARN, CRIT = Band(Decimal("5"), ThresholdUnit.PERCENT, Severity.WARNING), Band(Decimal("10"), ThresholdUnit.PERCENT, Severity.CRITICAL)


def _row(name, row_id):
    return SettingsRow(
        id=row_id, name=name, type=NotificationType.MONITORING, module=NotificationModule.MONITORING,
        scope=NotificationScope.GLOBAL, channels=("EMAIL",), recipient_roles={"ADMIN": True}, bands=(WARN, CRIT),
    )


SNAPSHOT = SettingsSnapshot(
    built_at="2026-09-30T06:57:00.000Z",
    rows={
        NotificationName.ERROR_RATE_5XX.value: _row(NotificationName.ERROR_RATE_5XX, 11),
        NotificationName.ERROR_RATE_4XX.value: _row(NotificationName.ERROR_RATE_4XX, 10),
    },
)


@asynccontextmanager
async def _session():
    yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


@pytest.fixture
def rt(monkeypatch):
    """A runtime with every ledger row absent (so every band crossing
    fires), a recorded claim per item and a recorded publish per event."""
    runtime = MagicMock()
    runtime.config.notif_monitor_cooldown_s = 1800
    runtime.cache.peek_settings.return_value = SNAPSHOT
    runtime.cache.write_ledger = AsyncMock()
    runtime.failures.record = AsyncMock()
    runtime.core_session_factory = _session
    runtime.auth_session_factory = _session
    runtime.recipients.for_roles = AsyncMock(return_value=[Recipient("admin@example.com", "Admin")])
    runtime.publisher.send = AsyncMock(return_value=True)
    runtime.claims = []
    runtime.lost = set()

    async def read(*, tenant_ids=(), ledger_refs=(), context_name=None):
        return CacheRead(settings=SNAPSHOT, ledger={ref.key: NO_LEDGER_ROW for ref in ledger_refs})

    async def claim_band(session, notification_id, ref, band_value, event_id):
        runtime.claims.append((ref.subject_dict["service_id"], band_value, event_id))
        if ref.subject_dict["service_id"] in runtime.lost:
            return None
        return LedgerState(True, band_value, True, utc_now())

    runtime.cache.read = read
    monkeypatch.setattr(pipeline, "get_runtime", lambda: runtime)
    monkeypatch.setattr(pipeline, "claim_band", claim_band)
    monkeypatch.setattr(pipeline, "reread", AsyncMock(return_value=NO_LEDGER_ROW))
    return runtime


def _details(context):
    return [str(context.band.value), "30 Sep 2026, 12:27 PM IST", str(context.observed.value), context.subject["service_id"]]


def _merge(parts):
    return ["merged", [p[3] for p in parts]]


def _item(service, value, name=NotificationName.ERROR_RATE_5XX, group=_merge):
    return BandItem(
        name=name, tenant_id=PLATFORM_TENANT_ID, subject=monitoring_subject(service),
        observed=Measurement(Decimal(value), ThresholdUnit.PERCENT), details=_details, group_details=group,
    )


def _envelopes(rt):
    return [call.args[0] for call in rt.publisher.send.await_args_list]


@pytest.mark.asyncio
async def test_services_over_one_alert_in_one_tick_are_one_event(rt):
    """12:27 — asr, llm and tts all cross 5xx in one tick: one email, all three."""
    sent = await emit_band_batch([_item("asr-service", "9.1"), _item("llm-service", "6.2"), _item("tts-service", "11.3")])

    (envelope,) = _envelopes(rt)
    assert sent == [envelope.event_id]
    assert envelope.details == ["merged", ["asr-service", "llm-service", "tts-service"]]
    # Each service keeps its own ledger row, all pointing at the one event.
    assert [(s, b) for s, b, _ in rt.claims] == [
        ("asr-service", Decimal("5")), ("llm-service", Decimal("5")), ("tts-service", Decimal("10")),
    ]
    assert {event_id for *_, event_id in rt.claims} == {envelope.event_id}
    # The highest band sets band and severity; a group has no single subject.
    assert envelope.band == CRIT and envelope.severity is Severity.CRITICAL
    assert envelope.subject == {}
    assert rt.recipients.for_roles.await_count == 1


@pytest.mark.asyncio
async def test_a_service_that_fires_alone_keeps_its_own_event(rt):
    await emit_band_batch([_item("asr-service", "9.1"), _item("llm-service", "0.5")])

    (envelope,) = _envelopes(rt)
    assert envelope.details == ["5", "30 Sep 2026, 12:27 PM IST", "9.1", "asr-service"]
    assert envelope.subject == {"service_id": "asr-service"}


@pytest.mark.asyncio
async def test_each_alert_is_its_own_group(rt):
    await emit_band_batch([
        _item("asr-service", "9.1"), _item("llm-service", "6.2"),
        _item("asr-service", "7", name=NotificationName.ERROR_RATE_4XX),
    ])

    by_name = {e.event_name: e for e in _envelopes(rt)}
    assert by_name[NotificationName.ERROR_RATE_5XX].details == ["merged", ["asr-service", "llm-service"]]
    assert by_name[NotificationName.ERROR_RATE_4XX].details[3] == "asr-service"


@pytest.mark.asyncio
async def test_a_service_whose_claim_is_lost_is_left_out(rt):
    """Another pod already fired llm at this band: only asr and tts are listed."""
    rt.lost = {"llm-service"}

    await emit_band_batch([_item("asr-service", "9.1"), _item("llm-service", "6.2"), _item("tts-service", "11.3")])

    (envelope,) = _envelopes(rt)
    assert envelope.details == ["merged", ["asr-service", "tts-service"]]


@pytest.mark.asyncio
async def test_items_without_group_details_are_one_event_each(rt):
    await emit_band_batch([_item("asr-service", "9.1", group=None), _item("llm-service", "6.2", group=None)])

    envelopes = _envelopes(rt)
    assert [e.subject["service_id"] for e in envelopes] == ["asr-service", "llm-service"]
    assert len({e.event_id for e in envelopes}) == 2


@pytest.mark.asyncio
async def test_a_failing_merge_sends_the_highest_band_service_and_writes_details_partial(rt):
    def broken(parts):
        raise ValueError("bad part")

    await emit_band_batch([_item("asr-service", "9.1", group=broken), _item("tts-service", "11.3", group=broken)])

    (envelope,) = _envelopes(rt)
    assert envelope.details == ["10", "30 Sep 2026, 12:27 PM IST", "11.3", "tts-service"]
    assert _failure_rows(rt) == [
        ("DETAILS_PARTIAL", {"service_id": "asr-service"}, envelope.event_id),
        ("DETAILS_PARTIAL", {"service_id": "tts-service"}, envelope.event_id),
    ]


# ── Failure rows of a grouped event name every service in it ─────────────


THREE = ("asr-service", "9.1"), ("llm-service", "6.2"), ("tts-service", "11.3")


def _failure_rows(rt):
    return [
        (call.args[1].value, call.kwargs["subject"], call.kwargs.get("event_id"))
        for call in rt.failures.record.await_args_list
    ]


@pytest.mark.asyncio
async def test_a_grouped_event_with_no_recipients_writes_one_row_per_service(rt):
    """12:27 — asr, llm and tts cross 5xx but nobody holds the role: each
    service's row says so, instead of one row with an empty subject."""
    rt.recipients.for_roles = AsyncMock(return_value=[])

    assert await emit_band_batch([_item(s, v) for s, v in THREE]) == []

    rows = _failure_rows(rt)
    assert [(code, subject) for code, subject, _ in rows] == [
        ("NO_RECIPIENTS", {"service_id": "asr-service"}),
        ("NO_RECIPIENTS", {"service_id": "llm-service"}),
        ("NO_RECIPIENTS", {"service_id": "tts-service"}),
    ]
    assert len({event_id for *_, event_id in rows}) == 1
    rt.publisher.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_grouped_event_whose_recipient_lookup_fails_writes_one_row_per_service(rt):
    rt.recipients.for_roles = AsyncMock(side_effect=RuntimeError("auth db down"))

    await emit_band_batch([_item(s, v) for s, v in THREE])

    assert [(code, subject["service_id"]) for code, subject, _ in _failure_rows(rt)] == [
        ("RECIPIENTS_LOOKUP_FAILED", "asr-service"),
        ("RECIPIENTS_LOOKUP_FAILED", "llm-service"),
        ("RECIPIENTS_LOOKUP_FAILED", "tts-service"),
    ]


@pytest.mark.asyncio
async def test_a_grouped_envelope_carries_every_service_and_a_single_one_does_not(rt):
    await emit_band_batch([_item(s, v) for s, v in THREE] + [_item("asr-service", "7", name=NotificationName.ERROR_RATE_4XX)])

    by_name = {e.event_name: e for e in _envelopes(rt)}
    grouped, single = by_name[NotificationName.ERROR_RATE_5XX], by_name[NotificationName.ERROR_RATE_4XX]
    assert grouped.to_json()["subjects"] == [
        {"service_id": "asr-service"}, {"service_id": "llm-service"}, {"service_id": "tts-service"},
    ]
    # A single-service message is unchanged on the wire.
    assert "subjects" not in single.to_json()
    assert single.to_json()["subject"] == {"service_id": "asr-service"}


@pytest.mark.asyncio
async def test_a_grouped_event_whose_kafka_send_fails_writes_one_row_per_service(monkeypatch):
    from ai4i_core.kafka import publisher as publisher_module
    from ai4i_core.kafka.publisher import Envelope, Publisher

    def broken():
        raise RuntimeError("broker down")

    monkeypatch.setattr(publisher_module, "get_kafka_producer_client", broken)
    failures = MagicMock(record=AsyncMock())
    subjects = [monitoring_subject(s) for s, _ in THREE]
    envelope = Envelope(
        event_id=pipeline.uuid.uuid4(), event_name=NotificationName.ERROR_RATE_5XX,
        notification_type=NotificationType.MONITORING, tenant_id=PLATFORM_TENANT_ID, tenant_name=None,
        subject={}, occurred_at=utc_now(), channels=("EMAIL",), severity=Severity.CRITICAL, details=[],
        recipients=[Recipient("admin@example.com", "Admin")], subjects=subjects,
    )

    assert await Publisher("notification.events", failures).send(envelope, notification_id=11) is False

    rows = [(c.args[1].value, c.kwargs["subject"], c.kwargs["event_id"]) for c in failures.record.await_args_list]
    assert rows == [("KAFKA_SEND_FAILED", s, envelope.event_id) for s in subjects]
