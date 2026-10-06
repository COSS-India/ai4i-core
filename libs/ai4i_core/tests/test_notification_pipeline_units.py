"""Unit tests of the shared notification pipeline pieces in ai4i_core.kafka:
subjects and keys, the BAND decision table, band selection, value JSON forms,
invalidation messages and failure-log throttling."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ai4i_core.kafka import constants as c
from ai4i_core.kafka.bands import band_for
from ai4i_core.kafka.constants import (
    Decision,
    FailureCode,
    FailureStage,
    InvalidationKind,
    NotificationName,
    Operation,
    Producer,
    Severity,
    ThresholdUnit,
)
from ai4i_core.kafka.failure_log import FailureLogger
from ai4i_core.kafka.invalidation import build_message, parse_message
from ai4i_core.kafka.keys import (
    InvalidSubject,
    budget_subject,
    format_amount,
    kafka_message_key,
    ledger_key,
    quota_subject,
    state_hash,
    subject_key,
    validate_subject,
)
from ai4i_core.kafka.ledger import decide
from ai4i_core.kafka.models import NO_LEDGER_ROW, Band, LedgerState, SettingsSnapshot, TenantSubscriptions
from ai4i_core.kafka.specs import SPECS, get_spec

NOW = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
COOLDOWN = 1800


def _bands(*values, unit=ThresholdUnit.PERCENT):
    severities = [Severity.INFO] * len(values)
    severities[-1] = Severity.CRITICAL
    if len(values) > 1:
        severities[-2] = Severity.WARNING
    return tuple(Band(Decimal(v), unit, s) for v, s in zip(values, severities))


def _state(band, triggered=True, age_s=0):
    return LedgerState(True, Decimal(band) if band is not None else None, triggered, NOW - timedelta(seconds=age_s))


# ── specs ────────────────────────────────────────────────────────────────


def test_every_catalog_name_has_a_spec():
    assert set(SPECS) == set(NotificationName)
    assert get_spec("NOPE") is None
    assert get_spec("QUOTA_THRESHOLD").period_key.value == "billing_month"
    assert get_spec(NotificationName.BUDGET_EXHAUSTED).period_key.value == "budget_window"
    assert all(get_spec(n).resets for n in ("ERROR_RATE_4XX", "LATENCY_P99"))
    assert not get_spec("QUOTA_THRESHOLD").resets


# ── subjects and keys ────────────────────────────────────────────────────


def test_subject_validation():
    spec = get_spec("QUOTA_THRESHOLD")
    assert validate_subject(spec, quota_subject("2026-09", "ASR")) == {"billing_month": "2026-09", "model_task_type": "asr"}
    for bad in ({}, {"billing_month": "2026-13", "model_task_type": "asr"},
                {"billing_month": "2026-09", "model_task_type": "ASR"},
                {"billing_month": "2026-09", "model_task_type": "asr", "extra": "x"}):
        with pytest.raises(InvalidSubject):
            validate_subject(spec, bad)
    with pytest.raises(InvalidSubject):
        validate_subject(get_spec("BUDGET_THRESHOLD"), {"budget_ceiling": "5000"})
    budget_spec = get_spec("BUDGET_THRESHOLD")
    assert validate_subject(budget_spec, budget_subject(Decimal("5000"), None, None)) == {
        "budget_ceiling": "5000.00", "budget_window": "none_none",
    }
    assert validate_subject(get_spec("TIER_CHANGED"), {}) == {}


def test_keys_and_amounts():
    subject = quota_subject("2026-09", "asr")
    assert subject_key(subject) == "billing_month=2026-09,model_task_type=asr"
    assert subject_key({}) == "_"
    assert ledger_key("QUOTA_THRESHOLD", "42", subject) == "ntf:v1:ledger:QUOTA_THRESHOLD:42:billing_month=2026-09,model_task_type=asr"
    assert kafka_message_key(NotificationName.TIER_CHANGED, "42", {}) == "TIER_CHANGED:42:_"
    assert budget_subject(Decimal("5000")) == {"budget_ceiling": "5000.00", "budget_window": "none_none"}
    from_dt = datetime(2026, 9, 17, tzinfo=timezone.utc)
    to_dt = datetime(2026, 10, 10, tzinfo=timezone.utc)
    assert budget_subject(Decimal("5000"), from_dt, to_dt) == {
        "budget_ceiling": "5000.00", "budget_window": f"{from_dt.isoformat()}_{to_dt.isoformat()}",
    }
    # A renewed/extended window (same ceiling, new end date) is a different
    # subject — the ledger row re-arms instead of staying claimed at the
    # previous window's highest band.
    assert budget_subject(Decimal("5000"), from_dt, to_dt) != budget_subject(Decimal("5000"), from_dt, datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert format_amount("8000.5") == "8000.50"


def test_state_hash_ignores_key_order():
    a = state_hash({"from_tier_id": "x", "to_tier_id": "y"})
    assert a == state_hash({"to_tier_id": "y", "from_tier_id": "x"})
    assert a != state_hash({"from_tier_id": "x", "to_tier_id": "z"})
    assert len(a) == 64


# ── BAND rule ────────────────────────────────────────────────────────────


def test_band_for_picks_highest_reached_band():
    bands = _bands(70, 80, 90)
    assert band_for(65, bands) is None
    assert band_for(70, bands).value == 70
    assert band_for(93, bands).value == 90
    assert band_for(93, bands).severity is Severity.CRITICAL


QUOTA = get_spec("QUOTA_THRESHOLD")
MONITOR = get_spec("ERROR_RATE_5XX")
B80 = Band(Decimal(80), ThresholdUnit.PERCENT, Severity.WARNING)
B90 = Band(Decimal(90), ThresholdUnit.PERCENT, Severity.CRITICAL)


@pytest.mark.parametrize(
    "spec, band, state, expected",
    [
        (QUOTA, None, NO_LEDGER_ROW, Decision.SKIP),                        # no band, no row
        (QUOTA, B80, NO_LEDGER_ROW, Decision.FIRE),                         # first band
        (QUOTA, B90, _state(80), Decision.FIRE),                            # escalation
        (QUOTA, B80, _state(80), Decision.SKIP),                            # same band
        (QUOTA, B80, _state(90), Decision.SKIP),                            # lower band
        (QUOTA, None, _state(90, age_s=99999), Decision.SKIP),              # metering never resets
        (MONITOR, None, _state(5, age_s=COOLDOWN - 1), Decision.SKIP),      # cooldown not over
        (MONITOR, None, _state(5, age_s=COOLDOWN), Decision.RESET),         # cooldown over
        (MONITOR, B80, _state(90, triggered=False), Decision.FIRE),         # re-armed row fires again
    ],
)
def test_decision_table(spec, band, state, expected):
    assert decide(spec, band, state, NOW, COOLDOWN) is expected


# ── JSON forms ───────────────────────────────────────────────────────────


def test_settings_snapshot_round_trip_stores_roles_not_recipient_ids():
    data = {
        "schema_version": 1,
        "built_at": "2026-09-28T10:15:00.000Z",
        "rows": {
            "QUOTA_THRESHOLD": {"id": 8, "type": "ALERT", "module": "QUOTA", "scope": "GLOBAL",
                                "channels": ["EMAIL"], "recipient_roles": {"ADMIN": True, "TENANT ADMIN": False},
                                "bands": [{"value": 90, "unit": "PERCENT", "severity": "CRITICAL"},
                                          {"value": 80, "unit": "PERCENT", "severity": "WARNING"}]},
            "ERROR_RATE_5XX": {"id": 11, "type": "MONITORING", "module": "MONITORING", "scope": "GLOBAL",
                               "channels": ["EMAIL"], "recipient_roles": {"ADMIN": True, "MODERATOR": False},
                               "bands": [{"value": 5, "unit": "PERCENT", "severity": "CRITICAL"}],
                               # an older snapshot's frozen ids are ignored
                               "recipient_user_ids": ["u1"]},
        },
    }
    snapshot = SettingsSnapshot.from_json(data)
    assert [b.value for b in snapshot.get("QUOTA_THRESHOLD").bands] == [80, 90]
    out = snapshot.to_json()
    assert all("recipient_user_ids" not in row for row in out["rows"].values())
    assert snapshot.get("ERROR_RATE_5XX").enabled_roles() == ("ADMIN",)
    assert SettingsSnapshot.from_json(out) == snapshot


def test_ledger_state_and_subscriptions_round_trip():
    state = _state(80)
    assert LedgerState.from_json(state.to_json()) == state
    assert NO_LEDGER_ROW.to_json() == {"exists": False, "current_band": None, "triggered": False, "triggered_at": None}
    subs = TenantSubscriptions.from_json({"tenant_id": "42", "built_at": "x",
                                          "rows": {"TIER_ASSIGNED": {"subscribed": True, "recipients": ["118"]}}})
    assert subs.entry("TIER_ASSIGNED").recipients == ("118",)
    assert subs.entry("BUDGET_ASSIGNED").subscribed is False


# ── invalidation ─────────────────────────────────────────────────────────


def test_invalidation_message_round_trip():
    raw = build_message(InvalidationKind.LEDGER, "svc/pod/pid-1", names=[NotificationName.QUOTA_THRESHOLD], keys=["k1"])
    message = parse_message(raw)
    assert message.kind is InvalidationKind.LEDGER
    assert message.names == ("QUOTA_THRESHOLD",) and message.keys == ("k1",)
    assert parse_message("not json") is None
    assert parse_message('{"v": 99, "kind": "FLUSH"}') is None


# ── failure log ──────────────────────────────────────────────────────────


class _Session:
    def __init__(self, sink):
        self.sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params):
        self.sink.append(params)

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_failures_without_event_id_are_throttled_and_counted():
    rows, clock = [], [0.0]
    log = FailureLogger(lambda: _Session(rows), Producer.PAYPERUSE_CONSUMER, "pod-1", 60, clock=lambda: clock[0])
    args = dict(notification_name="QUOTA_THRESHOLD", tenant_id="42", operation=Operation.SETTINGS_FILL)
    await log.record(FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, **args)
    await log.record(FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, **args)
    await log.record(FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, **args)
    assert len(rows) == 1
    clock[0] = 61
    await log.record(FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, **args)
    assert len(rows) == 2
    assert '"suppressed":2' in rows[1]["error_detail"]


@pytest.mark.asyncio
async def test_failures_with_event_id_are_never_throttled_and_never_raise():
    rows = []
    log = FailureLogger(lambda: _Session(rows), Producer.AUTH_SERVICE, None, 60)
    import uuid

    for _ in range(3):
        await log.record(FailureStage.PUBLISH, FailureCode.KAFKA_SEND_FAILED, notification_name="TIER_CHANGED",
                         operation=Operation.KAFKA_SEND, event_id=uuid.uuid4(), error=RuntimeError("down"))
    assert len(rows) == 3
    assert rows[0]["error_message"] == "down"

    def broken():
        raise RuntimeError("db down")

    await FailureLogger(broken, Producer.AUTH_SERVICE, None, 60).record(
        FailureStage.CACHE, FailureCode.CACHE_WRITE_FAILED, notification_name="*", operation=Operation.CACHE_WRITE
    )


@pytest.mark.asyncio
async def test_names_that_can_fire_needs_enabled_bands_and_someone_assigned(monkeypatch):
    from types import SimpleNamespace

    from ai4i_core.kafka import pipeline
    from ai4i_core.kafka.constants import NotificationModule, NotificationType
    from ai4i_core.kafka.models import SettingsRow, SubscriptionEntry

    def row(name, scope, roles, bands=(Decimal("80"),)):
        return SettingsRow(
            id=1, name=name, type=NotificationType.ALERT, module=NotificationModule.BUDGET,
            scope=scope, channels=("EMAIL",), recipient_roles=roles, bands=_bands(*bands) if bands else (),
        )

    rows = {
        NotificationName.BUDGET_THRESHOLD: row(NotificationName.BUDGET_THRESHOLD, c.NotificationScope.INSTITUTION, {"ADMIN": False}),
        NotificationName.BUDGET_EXHAUSTED: row(NotificationName.BUDGET_EXHAUSTED, c.NotificationScope.GLOBAL, {"ADMIN": True}),
    }
    subs = TenantSubscriptions(tenant_id="7", built_at="x", rows={
        NotificationName.BUDGET_THRESHOLD.value: SubscriptionEntry(subscribed=True, recipients=("u1",)),
    })

    async def read(**kwargs):
        return SimpleNamespace(settings=SimpleNamespace(get=rows.get), subscriptions={"7": subs})

    cache = SimpleNamespace(read=read, peek_settings=lambda: None, peek_subscriptions=lambda tenant: None)
    monkeypatch.setattr(pipeline, "get_runtime", lambda: SimpleNamespace(cache=cache))
    names = (NotificationName.BUDGET_THRESHOLD, NotificationName.BUDGET_EXHAUSTED)

    assert await pipeline.names_that_can_fire(names, "7") == list(names)

    # Unsubscribed and no role: the INSTITUTION row drops out.
    subs.rows.clear()
    assert await pipeline.names_that_can_fire(names, "7") == [NotificationName.BUDGET_EXHAUSTED]

    # Subscribed, but no role enabled and no extras added: _someone_assigned
    # is unconditionally True for NOTIFICATION/ALERT rows now — scope alone
    # decides who (this tenant's own Tenant Admins are always included),
    # not a role flag or extras. This is the exact shape of the originally
    # reported bug: an institution subscribed to a notification, with
    # nobody individually added, must still be able to fire. Reverting
    # _someone_assigned to the old `any_role_enabled() or extras` check
    # must fail this assertion.
    rows[NotificationName.BUDGET_THRESHOLD] = row(
        NotificationName.BUDGET_THRESHOLD, c.NotificationScope.INSTITUTION, {"ADMIN": False, "TENANT ADMIN": False},
    )
    subs.rows[NotificationName.BUDGET_THRESHOLD.value] = SubscriptionEntry(subscribed=True, recipients=())
    assert await pipeline.names_that_can_fire(names, "7") == list(names)

    # No active bands: nothing can fire.
    rows[NotificationName.BUDGET_THRESHOLD] = row(
        NotificationName.BUDGET_THRESHOLD, c.NotificationScope.INSTITUTION, {"ADMIN": False, "TENANT ADMIN": False}, bands=(),
    )
    rows[NotificationName.BUDGET_EXHAUSTED] = row(
        NotificationName.BUDGET_EXHAUSTED, c.NotificationScope.GLOBAL, {"ADMIN": True}, bands=()
    )
    assert await pipeline.names_that_can_fire(names, "7") == []


@pytest.mark.asyncio
async def test_names_that_can_fire_logs_settings_unavailable(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from ai4i_core.kafka import pipeline

    async def read(**kwargs):
        return SimpleNamespace(settings=None, settings_error=RuntimeError("db down"), subscriptions={})

    failures = SimpleNamespace(record=AsyncMock())
    cache = SimpleNamespace(read=read, peek_settings=lambda: None, peek_subscriptions=lambda tenant: None)
    monkeypatch.setattr(pipeline, "get_runtime", lambda: SimpleNamespace(cache=cache, failures=failures))

    assert await pipeline.names_that_can_fire((NotificationName.BUDGET_THRESHOLD,), "7") == []
    stage, code = failures.record.await_args.args
    assert stage is c.FailureStage.SETTINGS and code is c.FailureCode.SETTINGS_UNAVAILABLE


def test_failure_rows_store_the_qualified_exception_name():
    from ai4i_core.kafka.failure_log import _qualified_name

    class Boom(Exception):
        pass

    assert _qualified_name(ValueError("x")) == "ValueError"
    assert _qualified_name(Boom()).endswith("test_failure_rows_store_the_qualified_exception_name.<locals>.Boom")
