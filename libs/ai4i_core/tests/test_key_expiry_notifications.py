"""GRACE_PERIOD_EXPIRING / API_KEY_EXPIRING in the shared pipeline: their
subject (api_key_id, expires_at, days_before), each item's own severity in
emit_state_bulk, and the platform ADMIN as a recipient of each event (the
one consolidated ADMIN copy stays QUOTA_LIMIT_UPDATED's)."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai4i_core.kafka import pipeline
from ai4i_core.kafka.cache import CacheRead
from ai4i_core.kafka.constants import (
    NotificationModule,
    NotificationName,
    NotificationScope,
    NotificationType,
    Severity,
)
from ai4i_core.kafka.keys import InvalidSubject, utc_seconds, validate_subject
from ai4i_core.kafka.models import Recipient, SettingsRow, SettingsSnapshot
from ai4i_core.kafka.pipeline import StateItem, emit_state_bulk
from ai4i_core.kafka.specs import get_spec

NAME = NotificationName.GRACE_PERIOD_EXPIRING
VALID_SUBJECT = {"api_key_id": "901", "expires_at": "2026-11-27T10:30:00Z", "days_before": "10"}


def _row(admin: bool) -> SettingsRow:
    return SettingsRow(
        id=31, name=NAME, type=NotificationType.NOTIFICATION, module=NotificationModule.API_KEY,
        scope=NotificationScope.GLOBAL, channels=("EMAIL",),
        recipient_roles={"ADMIN": admin, "TENANT ADMIN": True}, bands=(),
    )


@asynccontextmanager
async def _session():
    yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def _runtime(monkeypatch, admin: bool):
    row = _row(admin)
    runtime = MagicMock()
    runtime.failures.record = AsyncMock()
    runtime.core_session_factory = _session
    runtime.auth_session_factory = _session
    runtime.publisher.send = AsyncMock(return_value=True)

    async def read(*, tenant_ids=(), context_name=None, ledger_refs=()):
        return CacheRead(settings=SettingsSnapshot(built_at="2026-11-17T00:00:00.000Z", rows={row.name.value: row}))

    async def claim_state_bulk(session, notification_id, claims):
        return list(claims)

    async def for_tenants(session, tenant_ids, recipient_roles, extra_user_ids):
        by_tenant = {t: [Recipient(f"ta{t}@x.io", f"Admin {t}")] for t in tenant_ids}
        admins = [Recipient("admin@x.io", "Adopter Admin")] if recipient_roles.get("ADMIN") else []
        return by_tenant, admins

    runtime.cache.read = read
    runtime.recipients.for_tenants = for_tenants
    monkeypatch.setattr(pipeline, "get_runtime", lambda: runtime)
    monkeypatch.setattr(pipeline, "claim_state_bulk", claim_state_bulk)
    return runtime


def _item(tenant_id: str, key_id: str, days_before: int, severity: Severity) -> StateItem:
    return StateItem(
        tenant_id=tenant_id,
        subject={"api_key_id": key_id, "expires_at": "2026-11-27T10:30:00Z", "days_before": str(days_before)},
        new_state={"days_before": days_before},
        details=["Billing App", f"prod-key (ID {key_id})", "Asha", "17 Nov 2026", "27 Nov 2026", days_before],
        tenant_name=f"Institution {tenant_id}",
        severity=severity,
    )


def _envelopes(runtime):
    return [call.args[0] for call in runtime.publisher.send.await_args_list]


@pytest.mark.parametrize("name", [NotificationName.GRACE_PERIOD_EXPIRING, NotificationName.API_KEY_EXPIRING])
def test_spec_is_state_with_key_expiry_subject(name):
    spec = get_spec(name)
    assert spec.is_state
    assert validate_subject(spec, VALID_SUBJECT) == VALID_SUBJECT


@pytest.mark.parametrize(
    "bad",
    [
        {**VALID_SUBJECT, "expires_at": "2026-11-27T10:30:00.123Z"},
        {**VALID_SUBJECT, "expires_at": "2026-11-27 10:30:00"},
        {**VALID_SUBJECT, "days_before": "0"},
        {**VALID_SUBJECT, "days_before": "-1"},
        {**VALID_SUBJECT, "api_key_id": "abc"},
        {"api_key_id": "901", "expires_at": "2026-11-27T10:30:00Z"},
    ],
)
def test_invalid_subject_is_rejected(bad):
    with pytest.raises(InvalidSubject):
        validate_subject(get_spec(NAME), bad)


def test_utc_seconds_is_utc_whole_seconds():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert utc_seconds(datetime(2026, 11, 27, 16, 0, 0, 999999, tzinfo=ist)) == "2026-11-27T10:30:00Z"


@pytest.mark.asyncio
async def test_each_event_carries_its_own_severity(monkeypatch):
    runtime = _runtime(monkeypatch, admin=False)
    sent = await emit_state_bulk(NAME, [
        _item("7", "901", 10, Severity.INFO),
        _item("8", "902", 1, Severity.CRITICAL),
    ])
    assert len(sent) == 2
    by_key = {e.subject["api_key_id"]: e for e in _envelopes(runtime)}
    assert by_key["901"].severity is Severity.INFO
    assert by_key["902"].severity is Severity.CRITICAL
    assert [r.email for r in by_key["901"].recipients] == ["ta7@x.io"]


@pytest.mark.asyncio
async def test_admin_is_a_recipient_of_each_event_not_one_consolidated_copy(monkeypatch):
    runtime = _runtime(monkeypatch, admin=True)
    await emit_state_bulk(NAME, [
        _item("7", "901", 5, Severity.WARNING),
        _item("8", "902", 5, Severity.WARNING),
    ])
    envelopes = _envelopes(runtime)
    assert len(envelopes) == 2
    for envelope in envelopes:
        assert "admin@x.io" in {r.email for r in envelope.recipients}
        assert envelope.tenant_id in ("7", "8")
