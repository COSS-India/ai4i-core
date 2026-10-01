"""emit_state_bulk: the platform ADMIN gets exactly one consolidated copy
for the whole call — naming every tenant that fired and every change across
every changed subject (e.g. every model task type on a tier) — instead of
one copy per tenant or per subject. AI4IDS-3296: Quota Limit Updated sent
the Adopter Admin once per institution on the tier instead of one email
listing all of them."""

from contextlib import asynccontextmanager
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
)
from ai4i_core.kafka.keys import utc_now
from ai4i_core.kafka.ledger import StateClaim
from ai4i_core.kafka.models import Recipient, SettingsRow, SettingsSnapshot
from ai4i_core.kafka.pipeline import StateItem, emit_state_bulk

ROW = SettingsRow(
    id=21, name=NotificationName.QUOTA_LIMIT_UPDATED, type=NotificationType.NOTIFICATION,
    module=NotificationModule.QUOTA, scope=NotificationScope.GLOBAL, channels=("EMAIL",),
    recipient_roles={"ADMIN": True}, bands=(),
)
SNAPSHOT = SettingsSnapshot(built_at="2026-10-01T00:00:00.000Z", rows={ROW.name.value: ROW})

TENANT_ADMINS = {
    "7": [Recipient("ta7@x.io", "Force India Admin")],
    "8": [Recipient("ta8@x.io", "Mahindra India Admin")],
    "9": [Recipient("ta9@x.io", "Maruthi Tele Admin")],
}
TENANT_NAMES = {"7": "Force India", "8": "Mahindra India", "9": "Maruthi Tele"}


@asynccontextmanager
async def _session():
    yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


@pytest.fixture
def rt(monkeypatch):
    runtime = MagicMock()
    runtime.failures.record = AsyncMock()
    runtime.core_session_factory = _session
    runtime.auth_session_factory = _session
    runtime.publisher.send = AsyncMock(return_value=True)

    async def read(*, tenant_ids=(), context_name=None, ledger_refs=()):
        return CacheRead(settings=SNAPSHOT)

    async def claim_state_bulk(session, notification_id, claims):
        return list(claims)  # every claim wins

    async def for_tenants(session, tenant_ids, recipient_roles, extra_user_ids):
        by_tenant = {t: TENANT_ADMINS.get(t, []) for t in tenant_ids}
        admins = [Recipient("admin@x.io", "Adopter Admin")] if recipient_roles.get("ADMIN") else []
        return by_tenant, admins

    runtime.cache.read = read
    runtime.recipients.for_tenants = for_tenants
    monkeypatch.setattr(pipeline, "get_runtime", lambda: runtime)
    monkeypatch.setattr(pipeline, "claim_state_bulk", claim_state_bulk)
    return runtime


def _item(tenant_id, task="asr"):
    return StateItem(
        tenant_id=tenant_id, tenant_name=TENANT_NAMES[tenant_id], subject={"model_task_type": task},
        new_state={"to_quota": "20000"}, details=["Master Tier", [f"{task.upper()}: changed to 20000"], "2026-11-01"],
    )


def _envelopes(rt):
    return [call.args[0] for call in rt.publisher.send.await_args_list]


@pytest.mark.asyncio
async def test_admin_gets_one_consolidated_email_not_one_per_institution(rt):
    """Master Tier, 3 institutions, one changed task: 3 per-tenant emails
    (unchanged) plus exactly 1 admin email naming all 3 — not 3 admin
    emails, which was the reported bug."""
    sent = await emit_state_bulk(NotificationName.QUOTA_LIMIT_UPDATED, [_item("7"), _item("8"), _item("9")])

    envelopes = _envelopes(rt)
    assert len(envelopes) == 4
    assert len(sent) == 4

    admin_envelopes = [e for e in envelopes if e.recipients == [Recipient("admin@x.io", "Adopter Admin")]]
    assert len(admin_envelopes) == 1
    (admin_envelope,) = admin_envelopes
    assert admin_envelope.tenant_id == PLATFORM_TENANT_ID
    assert admin_envelope.tenant_name == "multiple institutions"
    assert admin_envelope.details[:3] == ["Master Tier", ["ASR: changed to 20000"], "2026-11-01"]
    assert admin_envelope.details[3] == ["Force India", "Mahindra India", "Maruthi Tele"]

    # Each institution's own Tenant Admin still gets their own per-tenant
    # email, and it does not carry the Admin.
    tenant_envelopes = {e.tenant_id: e for e in envelopes if e.tenant_id != PLATFORM_TENANT_ID}
    assert set(tenant_envelopes) == {"7", "8", "9"}
    for tenant_id, envelope in tenant_envelopes.items():
        assert envelope.recipients == TENANT_ADMINS[tenant_id]
        assert envelope.tenant_name == TENANT_NAMES[tenant_id]


@pytest.mark.asyncio
async def test_admin_gets_one_consolidated_email_across_changed_tasks(rt):
    """Two task types changed on the same tier save: still exactly one
    admin email for the whole call, not one per task type and not one per
    (tenant, task) pair — its change list covers both tasks."""
    sent = await emit_state_bulk(
        NotificationName.QUOTA_LIMIT_UPDATED,
        [_item("7", "asr"), _item("8", "asr"), _item("7", "nmt"), _item("8", "nmt")],
    )

    envelopes = _envelopes(rt)
    admin_envelopes = [e for e in envelopes if e.tenant_id == PLATFORM_TENANT_ID]
    assert len(admin_envelopes) == 1
    (admin_envelope,) = admin_envelopes
    assert admin_envelope.subject == {}
    assert admin_envelope.to_json()["subjects"] == [{"model_task_type": "asr"}, {"model_task_type": "nmt"}]
    assert admin_envelope.details[1] == ["ASR: changed to 20000", "NMT: changed to 20000"]
    assert admin_envelope.details[3] == ["Force India", "Mahindra India"]
    assert len(sent) == 5  # 4 per-tenant + 1 consolidated admin


@pytest.mark.asyncio
async def test_single_institution_tier_sends_admin_the_same_single_name_not_the_plural_wording(rt):
    """A tier with only one institution: the Admin's copy still reads like
    today's single-institution email (its own name), not "multiple
    institutions" with a 1-item list."""
    await emit_state_bulk(NotificationName.QUOTA_LIMIT_UPDATED, [_item("7")])

    (admin_envelope,) = [e for e in _envelopes(rt) if e.tenant_id == PLATFORM_TENANT_ID]
    assert admin_envelope.tenant_name == "Force India"
    assert len(admin_envelope.details) == 3  # no institutions list appended


@pytest.mark.asyncio
async def test_admin_checkbox_unselected_sends_no_admin_email(rt):
    """The Adopter Admin checkbox (recipient_roles["ADMIN"]) still gates
    this consolidated copy, same as any per-tenant one."""
    monkeypatch_row = SettingsRow(
        id=ROW.id, name=ROW.name, type=ROW.type, module=ROW.module, scope=ROW.scope,
        channels=ROW.channels, recipient_roles={"ADMIN": False}, bands=(),
    )
    rt.cache.read = (lambda *, tenant_ids=(), context_name=None, ledger_refs=(): _read_with_row(monkeypatch_row))

    await emit_state_bulk(NotificationName.QUOTA_LIMIT_UPDATED, [_item("7"), _item("8")])

    envelopes = _envelopes(rt)
    assert all(e.tenant_id != PLATFORM_TENANT_ID for e in envelopes)
    assert {e.tenant_id for e in envelopes} == {"7", "8"}


async def _read_with_row(row):
    return CacheRead(settings=SettingsSnapshot(built_at=SNAPSHOT.built_at, rows={row.name.value: row}))
