"""consumers/notifications_consumer/handler.py — the dumb envelope-to-email
mapping and the one thing it still decides: whether to write a
notification_failures row.

No ledger, no config cache, no dedup any more — handler.py just parses the
envelope, calls delivery.deliver(), and records a failure (verbatim raw
message + channel) when nothing went out, for any reason at all, including
a malformed envelope. Nothing here touches a real database, Kafka, or SMTP:
delivery.deliver and failures.record_failure are faked.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from consumers.notifications_consumer.handler import CHANNEL, handle_notification_event


def _msg(payload: dict | bytes) -> MagicMock:
    msg = MagicMock()
    if isinstance(payload, bytes):
        msg.value.return_value = payload
    else:
        msg.value.return_value = json.dumps(payload).encode("utf-8")
    return msg


def _envelope(**overrides) -> dict:
    base = dict(
        event_name="TIER_CHANGED",
        tenant_name="Acme Bank",
        details=["A", "B", "Some tier"],
        recipients=[{"email": "a@example.com", "name": "A"}],
    )
    base.update(overrides)
    return base


def _db_session_scope_stub(db):
    @asynccontextmanager
    async def _scope(name=None):
        yield db
    return _scope


class TestHandleNotificationEvent:
    async def test_delivered_records_no_failure(self):
        db = object()
        with patch(
            "consumers.notifications_consumer.handler.delivery.deliver",
            AsyncMock(return_value=True),
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _db_session_scope_stub(db),
        ), patch(
            "consumers.notifications_consumer.handler.failures.record_failure", AsyncMock()
        ) as record:
            await handle_notification_event(_msg(_envelope()))

        record.assert_not_awaited()

    async def test_delivery_returning_false_records_failure(self):
        db = object()
        raw = json.dumps(_envelope()).encode("utf-8")
        with patch(
            "consumers.notifications_consumer.handler.delivery.deliver",
            AsyncMock(return_value=False),
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _db_session_scope_stub(db),
        ), patch(
            "consumers.notifications_consumer.handler.failures.record_failure", AsyncMock()
        ) as record:
            await handle_notification_event(_msg(raw))

        record.assert_awaited_once_with(db, message=raw, channel=CHANNEL)

    async def test_delivery_raising_still_records_failure(self):
        """A raise out of delivery.deliver (e.g. a template render miss) must
        not propagate — it's treated exactly like any other non-delivery and
        still gets a notification_failures row, never a wedged/lost event."""
        db = object()
        raw = json.dumps(_envelope()).encode("utf-8")
        with patch(
            "consumers.notifications_consumer.handler.delivery.deliver",
            AsyncMock(side_effect=RuntimeError("boom")),
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _db_session_scope_stub(db),
        ), patch(
            "consumers.notifications_consumer.handler.failures.record_failure", AsyncMock()
        ) as record:
            await handle_notification_event(_msg(raw))

        record.assert_awaited_once_with(db, message=raw, channel=CHANNEL)

    async def test_malformed_json_records_failure_without_calling_deliver(self):
        raw = b"not json at all"
        db = object()
        with patch(
            "consumers.notifications_consumer.handler.delivery.deliver", AsyncMock()
        ) as deliver, patch(
            "consumers.notifications_consumer.handler.session_scope",
            _db_session_scope_stub(db),
        ), patch(
            "consumers.notifications_consumer.handler.failures.record_failure", AsyncMock()
        ) as record:
            await handle_notification_event(_msg(raw))

        deliver.assert_not_awaited()
        record.assert_awaited_once_with(db, message=raw, channel=CHANNEL)

    async def test_missing_recipients_records_failure_without_calling_deliver(self):
        raw = json.dumps(_envelope(recipients=[])).encode("utf-8")
        db = object()
        with patch(
            "consumers.notifications_consumer.handler.delivery.deliver", AsyncMock()
        ) as deliver, patch(
            "consumers.notifications_consumer.handler.session_scope",
            _db_session_scope_stub(db),
        ), patch(
            "consumers.notifications_consumer.handler.failures.record_failure", AsyncMock()
        ) as record:
            await handle_notification_event(_msg(raw))

        deliver.assert_not_awaited()
        record.assert_awaited_once_with(db, message=raw, channel=CHANNEL)

    async def test_failure_recording_itself_raising_is_swallowed(self):
        """record_failure is the last line of defense — if even that fails
        (DB down), the handler must still not raise, or the whole consumer
        loop goes down over one bad message."""
        with patch(
            "consumers.notifications_consumer.handler.delivery.deliver",
            AsyncMock(return_value=False),
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _db_session_scope_stub(object()),
        ), patch(
            "consumers.notifications_consumer.handler.failures.record_failure",
            AsyncMock(side_effect=RuntimeError("db down")),
        ):
            await handle_notification_event(_msg(_envelope()))  # must not raise

    async def test_passes_envelope_fields_through_to_deliver(self):
        db = object()
        envelope = _envelope(
            event_name="BUDGET_ASSIGNED",
            tenant_name="Beta Org",
            details=["INR", "100"],
            recipients=[{"email": "x@example.com", "name": "X"}],
        )
        with patch(
            "consumers.notifications_consumer.handler.delivery.deliver",
            AsyncMock(return_value=True),
        ) as deliver, patch(
            "consumers.notifications_consumer.handler.session_scope",
            _db_session_scope_stub(db),
        ):
            await handle_notification_event(_msg(envelope))

        deliver.assert_awaited_once_with(
            tenant_name="Beta Org",
            recipients=[{"email": "x@example.com", "name": "X"}],
            event_name="BUDGET_ASSIGNED",
            details=["INR", "100"],
        )
