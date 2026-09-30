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
    stage, code = rt.failures.record.await_args.args
    assert (stage.value, code.value) == ("DETAILS", "DETAILS_PARTIAL")
