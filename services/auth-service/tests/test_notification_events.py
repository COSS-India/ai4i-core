"""app.services.notification_events — what auth-service hands to the shared
producer pipeline (ai4i_core.kafka.emit_state) for tier and budget changes,
and the Q-D1 tier details loader."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ai4i_core.kafka import NotificationName

import app.services.notification_events as events


@pytest.mark.asyncio
async def test_tier_events(monkeypatch):
    calls = []

    async def fake_emit_state(name, tenant_id, new_state, **kwargs):
        calls.append({"name": name, "tenant_id": tenant_id, "new_state": new_state, **kwargs})

    pending = []
    monkeypatch.setattr(events, "notifications_configured", lambda: True)
    monkeypatch.setattr(events, "emit_state", fake_emit_state)
    monkeypatch.setattr(events, "run_in_background", pending.append)

    old_tier, new_tier = uuid4(), uuid4()
    events.publish_tier_event(None, new_tier, "Gold", 7)
    events.publish_tier_event(old_tier, new_tier, "Gold", 7)
    for coroutine in pending:
        await coroutine

    assigned, changed = calls
    assert assigned["name"] is NotificationName.TIER_ASSIGNED
    assert assigned["tenant_id"] == "7"
    assert assigned["new_state"] == {"from_tier_id": None, "to_tier_id": str(new_tier)}
    assert assigned["fallback_details"] == ["Gold", "", []]
    assert changed["name"] is NotificationName.TIER_CHANGED
    assert changed["new_state"] == {"from_tier_id": str(old_tier), "to_tier_id": str(new_tier)}

    # The details loader runs Q-D1 once for both tiers.
    tiers = {
        str(new_tier): {"name": "Gold", "description": "High volume", "quotas": [{"inference_name": "asr", "monthly_quota": 10000}]},
        str(old_tier): {"name": "Silver", "description": "", "quotas": []},
    }
    monkeypatch.setattr(events, "_load_tier_details", AsyncMock(return_value=tiers))
    assert await assigned["details"]() == ["Gold", "High volume", ["ASR: 10,000 req/mo"]]
    assert await changed["details"]() == ["Silver", "Gold", "High volume", ["ASR: 10,000 req/mo"]]


@pytest.mark.asyncio
async def test_budget_events(monkeypatch):
    calls = []

    async def fake_emit_state(name, tenant_id, new_state, **kwargs):
        calls.append({"name": name, "tenant_id": tenant_id, "new_state": new_state, **kwargs})

    pending = []
    monkeypatch.setattr(events, "notifications_configured", lambda: True)
    monkeypatch.setattr(events, "emit_state", fake_emit_state)
    monkeypatch.setattr(events, "run_in_background", pending.append)

    revised = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    events.publish_budget_event(7, Decimal("0"), Decimal("500"), date(2026, 10, 1), revised_at=revised)
    events.publish_budget_event(7, Decimal("500"), Decimal("800.5"), None)
    for coroutine in pending:
        await coroutine

    assigned, updated = calls
    assert assigned["name"] is NotificationName.BUDGET_ASSIGNED
    assert assigned["new_state"] == {
        "amount": "500.00", "effective_from": "2026-10-01", "revised_at": "2026-09-29T10:00:00+00:00",
    }
    assert assigned["details"] == ["INR", "500"]
    assert updated["name"] is NotificationName.BUDGET_UPDATED
    assert updated["new_state"] == {"from_amount": "500.00", "to_amount": "800.50", "effective_from": None}
    assert updated["details"][:3] == ["INR", "500", "800.5"]


@pytest.mark.asyncio
async def test_reassigning_the_same_budget_after_a_top_down_to_zero_is_a_new_state(monkeypatch):
    # effective_from is locked once a window exists, so amount + window alone
    # would repeat; the committed revision time keeps the second assignment
    # from being dropped as a duplicate, while a retry of one commit matches.
    calls = []

    async def fake_emit_state(name, tenant_id, new_state, **kwargs):
        calls.append(new_state)

    pending = []
    monkeypatch.setattr(events, "notifications_configured", lambda: True)
    monkeypatch.setattr(events, "emit_state", fake_emit_state)
    monkeypatch.setattr(events, "run_in_background", pending.append)

    window = date(2026, 10, 1)
    first = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    second = datetime(2026, 9, 29, 11, 0, tzinfo=timezone.utc)
    events.publish_budget_event(7, Decimal("0"), Decimal("500"), window, revised_at=first)
    events.publish_budget_event(7, Decimal("0"), Decimal("500"), window, revised_at=first)
    events.publish_budget_event(7, Decimal("0"), Decimal("500"), window, revised_at=second)
    for coroutine in pending:
        await coroutine

    assert calls[0] == calls[1]
    assert calls[0] != calls[2]


def test_nothing_is_sent_when_the_pipeline_is_not_configured(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(events, "notifications_configured", lambda: False)
    monkeypatch.setattr(events, "run_in_background", run)
    events.publish_tier_event(None, uuid4(), "Gold", 7)
    events.publish_budget_event(7, Decimal("0"), Decimal("1"), None)
    events.refresh_tenant_subscriptions(7)
    run.assert_not_called()
