"""consumers/notifications_consumer/handler.py — v2 envelope parsing, the
event_id delivery claim, and the hand-off to delivery.deliver.

Nothing here touches a real database, Kafka, Redis or SMTP — delivery,
session_scope and the Redis client are faked.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from consumers.notifications_consumer import handler as h
from consumers.notifications_consumer.config import Constants


def _payload(**overrides) -> dict:
    base = dict(
        schema_version=2,
        event_id="6f1c0d52-4a36-4bb8-9a1c-2d4f7f0a8e11",
        event_name="TIER_CHANGED",
        notification_type="NOTIFICATION",
        tenant_id="2",
        tenant_name="acme",
        subject={},
        occurred_at="2026-09-11T00:00:00.000+00:00",
        channels=["EMAIL"],
        severity="INFO",
        band=None,
        observed=None,
        details=["A", "B", "Some tier", ["NMT: 10,000 req/mo"], "1000", "2026-09-10", "2027-09-09"],
        recipients=[{"email": "admin@example.com", "name": "Asha"}],
    )
    base.update(overrides)
    return base


def _msg(payload) -> SimpleNamespace:
    raw = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
    return SimpleNamespace(value=lambda: raw, topic=lambda: "t", partition=lambda: 0, offset=lambda: 1)


def _scope_stub(auth_db):
    @asynccontextmanager
    async def _scope(name=None):
        yield auth_db
    return _scope


class _Redis:
    def __init__(self, won=True, raises=False):
        self.won, self.raises, self.calls = won, raises, []

    async def set(self, key, value, nx=False, ex=None):
        self.calls.append((key, nx, ex))
        if self.raises:
            raise ConnectionError("redis down")
        return self.won


class TestParseEnvelope:
    def test_v2_envelope_is_parsed(self):
        envelope = h._parse_envelope(_msg(_payload()))
        assert envelope["event_id"] == "6f1c0d52-4a36-4bb8-9a1c-2d4f7f0a8e11"
        assert envelope["channels"] == ["EMAIL"]
        assert envelope["recipients"] == [{"email": "admin@example.com", "name": "Asha"}]

    @pytest.mark.parametrize("overrides", [
        {"schema_version": 1},
        {"schema_version": None},
        {"event_id": None},
        {"event_name": ""},
        {"tenant_id": None},
    ])
    def test_unsupported_or_incomplete_envelopes_are_skipped(self, overrides):
        assert h._parse_envelope(_msg(_payload(**overrides))) is None

    def test_invalid_json_is_skipped(self):
        assert h._parse_envelope(_msg(b"{not json")) is None

    def test_recipients_without_email_are_dropped(self):
        envelope = h._parse_envelope(_msg(_payload(recipients=[{"name": "x"}, "bad", {"email": "a@b.c"}])))
        assert envelope["recipients"] == [{"email": "a@b.c"}]


class TestHandleNotificationEvent:
    async def _run(self, payload, redis):
        auth_db = object()
        deliver = AsyncMock(return_value="sent")
        with patch.object(h, "get_redis_client", lambda: redis), patch.object(
            h, "session_scope", _scope_stub(auth_db)
        ), patch.object(h.delivery, "deliver", deliver):
            await h.handle_notification_event(_msg(payload))
        return deliver, auth_db

    async def test_first_delivery_claims_the_event_id_and_delivers(self):
        redis = _Redis(won=True)
        deliver, auth_db = await self._run(_payload(), redis)

        key, nx, ex = redis.calls[0]
        assert key == f"{Constants.DELIVERY_CLAIM_KEY_PREFIX}6f1c0d52-4a36-4bb8-9a1c-2d4f7f0a8e11"
        assert nx is True and ex == Constants.DELIVERY_CLAIM_TTL_SECONDS
        deliver.assert_awaited_once()
        assert deliver.await_args.args == (auth_db,)
        assert deliver.await_args.kwargs == dict(
            tenant_id="2",
            recipients=[{"email": "admin@example.com", "name": "Asha"}],
            event_name="TIER_CHANGED",
            details=_payload()["details"],
            platform_level=False,
        )

    async def test_redelivery_of_a_claimed_event_is_not_sent_again(self):
        deliver, _ = await self._run(_payload(), _Redis(won=False))
        deliver.assert_not_awaited()

    async def test_redis_down_still_delivers(self):
        deliver, _ = await self._run(_payload(), _Redis(raises=True))
        deliver.assert_awaited_once()

    async def test_no_email_channel_is_skipped_without_claiming(self):
        redis = _Redis()
        deliver, _ = await self._run(_payload(channels=["SLACK"]), redis)
        deliver.assert_not_awaited()
        assert redis.calls == []

    async def test_monitoring_is_platform_level(self):
        deliver, _ = await self._run(
            _payload(notification_type="MONITORING", tenant_id="PLATFORM", tenant_name=None), _Redis()
        )
        assert deliver.await_args.kwargs["platform_level"] is True

    async def test_delivery_raising_does_not_propagate(self):
        with patch.object(h, "get_redis_client", lambda: _Redis()), patch.object(
            h, "session_scope", _scope_stub(object())
        ), patch.object(h.delivery, "deliver", AsyncMock(side_effect=RuntimeError("smtp"))):
            await h.handle_notification_event(_msg(_payload()))


class TestDeliver:
    async def test_names_from_the_envelope_greet_each_recipient(self):
        from consumers.notifications_consumer import delivery

        sent = []

        async def _send_one(*, recipient, institution_name, event_name, details):
            sent.append((recipient.email, recipient.display_name, institution_name))
            return True

        with patch.object(delivery.emailer, "send_one", _send_one), patch.object(
            delivery.recipients_lookup, "fetch_institution_name", AsyncMock(return_value="Acme Institute")
        ):
            outcome = await delivery.deliver(
                object(), tenant_id="2", event_name="TIER_CHANGED", details=[],
                recipients=[{"email": "a@x.io", "name": "Asha"}, {"email": "b@x.io", "name": None}],
            )

        assert outcome == "sent"
        assert sent == [("a@x.io", "Asha", "Acme Institute"), ("b@x.io", "there", "Acme Institute")]

    async def test_platform_level_skips_the_institution_lookup(self):
        from consumers.notifications_consumer import delivery

        lookup = AsyncMock()
        with patch.object(delivery.emailer, "send_one", AsyncMock(return_value=True)), patch.object(
            delivery.recipients_lookup, "fetch_institution_name", lookup
        ):
            outcome = await delivery.deliver(
                object(), tenant_id="PLATFORM", event_name="ERROR_RATE_5XX", details=[],
                recipients=[{"email": "a@x.io", "name": "Asha"}], platform_level=True,
            )

        assert outcome == "sent"
        lookup.assert_not_awaited()

    async def test_no_recipients(self):
        from consumers.notifications_consumer import delivery

        assert await delivery.deliver(
            object(), tenant_id="2", event_name="TIER_CHANGED", details=[], recipients=[]
        ) == "no_recipients"
