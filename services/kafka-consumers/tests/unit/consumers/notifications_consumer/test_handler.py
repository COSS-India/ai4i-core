"""consumers/notifications_consumer/handler.py — _process_channel's delivery
state machine.

_process_channel is the one place deciding, per channel, whether to touch a
ledger row at all, whether to claim the send, and how to settle it. The
happy path (claim -> deliver -> settle "sent") is the smallest slice of the
branches that matter here: a redelivery of an already-terminal row, a
stuck/unexpected in-between state, a non-EMAIL channel, a lost claim race,
and — the bug this suite exists to pin — a raise out of delivery.deliver
that must still settle the row to "failed" rather than leaving it wedged at
"sending" forever with no failed record and no automatic recovery (see the
comment above the try/except in handler.py itself).

Nothing here touches a real database, Kafka, or SMTP — ledger, delivery, and
session_scope are all faked; `db`/`auth_db` are opaque sentinels only ever
compared by identity.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from consumers.notifications_consumer.catalog_cache import NotificationConfig
from consumers.notifications_consumer.handler import _process_channel, handle_notification_event


def _cfg(**overrides) -> NotificationConfig:
    base = dict(
        id=1,
        name="TIER_CHANGED",
        type="NOTIFICATION",
        module="PAY_PER_USE",
        channels=["EMAIL"],
        thresholds=[],
    )
    base.update(overrides)
    return NotificationConfig(**base)


def _envelope(**overrides) -> dict:
    base = dict(
        event_name="TIER_CHANGED",
        tenant_id="2",
        occurred_at="2026-09-11T00:00:00+00:00",
        subject={},
        details=["A", "B", "Some tier", ["NMT: 10,000 req/mo"], "1000", "2026-09-10", "2027-09-09"],
        actor_id=None,
        recipients=["admin@example.com"],
    )
    base.update(overrides)
    return base


def _auth_session_scope_stub(auth_db):
    @asynccontextmanager
    async def _scope(name=None):
        yield auth_db
    return _scope


class TestProcessChannelStateMachine:
    async def test_no_ledger_row_does_nothing(self):
        db = object()
        with patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=None),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send", AsyncMock()
        ) as claim, patch(
            "consumers.notifications_consumer.handler.delivery.deliver", AsyncMock()
        ) as deliver, patch(
            "consumers.notifications_consumer.handler.ledger.mark_delivery", AsyncMock()
        ) as mark:
            await _process_channel(db, _cfg(), _envelope(), "EMAIL")

        claim.assert_not_awaited()
        deliver.assert_not_awaited()
        mark.assert_not_awaited()

    @pytest.mark.parametrize("terminal", ["sent", "failed", "skipped"])
    async def test_terminal_delivery_is_left_alone(self, terminal):
        # A genuine redelivery of an occurrence already fully handled.
        row = (1, {"value": "x", "delivery": terminal})
        db = object()
        with patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=row),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send", AsyncMock()
        ) as claim, patch(
            "consumers.notifications_consumer.handler.delivery.deliver", AsyncMock()
        ) as deliver:
            await _process_channel(db, _cfg(), _envelope(), "EMAIL")

        claim.assert_not_awaited()
        deliver.assert_not_awaited()

    async def test_unexpected_delivery_state_is_left_alone(self):
        # "sending" here means an earlier pass claimed the send and never
        # settled it (the exact scenario the new try/except now prevents
        # going forward) — a later redelivery must not touch it again.
        row = (1, {"value": "x", "delivery": "sending"})
        db = object()
        with patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=row),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send", AsyncMock()
        ) as claim, patch(
            "consumers.notifications_consumer.handler.delivery.deliver", AsyncMock()
        ) as deliver:
            await _process_channel(db, _cfg(), _envelope(), "EMAIL")

        claim.assert_not_awaited()
        deliver.assert_not_awaited()

    async def test_non_email_channel_is_marked_skipped_without_claiming(self):
        row = (1, {"value": "x", "delivery": "in_progress"})
        db = object()
        with patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=row),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send", AsyncMock()
        ) as claim, patch(
            "consumers.notifications_consumer.handler.ledger.mark_delivery", AsyncMock()
        ) as mark:
            await _process_channel(
                db, _cfg(channels=["SLACK"]), _envelope(), "SLACK"
            )

        claim.assert_not_awaited()
        mark.assert_awaited_once_with(db, row_id=1, delivery="skipped")

    async def test_lost_claim_race_does_not_deliver(self):
        row = (1, {"value": "x", "delivery": "in_progress"})
        db = object()
        with patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=row),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send",
            AsyncMock(return_value=False),
        ), patch(
            "consumers.notifications_consumer.handler.delivery.deliver", AsyncMock()
        ) as deliver, patch(
            "consumers.notifications_consumer.handler.ledger.mark_delivery", AsyncMock()
        ) as mark:
            await _process_channel(db, _cfg(), _envelope(), "EMAIL")

        deliver.assert_not_awaited()
        mark.assert_not_awaited()

    async def test_successful_delivery_settles_sent(self):
        row = (1, {"value": "x", "delivery": "in_progress"})
        db = object()
        auth_db = object()
        with patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=row),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send",
            AsyncMock(return_value=True),
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _auth_session_scope_stub(auth_db),
        ), patch(
            "consumers.notifications_consumer.handler.delivery.deliver",
            AsyncMock(return_value="sent"),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.mark_delivery", AsyncMock()
        ) as mark:
            await _process_channel(db, _cfg(), _envelope(), "EMAIL")

        mark.assert_awaited_once_with(db, row_id=1, delivery="sent")

    @pytest.mark.parametrize("outcome", ["no_recipients", "failed"])
    async def test_non_sent_outcome_settles_failed(self, outcome):
        row = (1, {"value": "x", "delivery": "in_progress"})
        db = object()
        auth_db = object()
        with patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=row),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send",
            AsyncMock(return_value=True),
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _auth_session_scope_stub(auth_db),
        ), patch(
            "consumers.notifications_consumer.handler.delivery.deliver",
            AsyncMock(return_value=outcome),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.mark_delivery", AsyncMock()
        ) as mark:
            await _process_channel(db, _cfg(), _envelope(), "EMAIL")

        mark.assert_awaited_once_with(db, row_id=1, delivery="failed")

    async def test_delivery_raising_still_settles_failed(self):
        """The bug this PR fixes: once claim_send has committed "sending",
        a raise anywhere in delivery.deliver (a decrypt failure, a template
        render miss, the auth DB dropping) must still reach mark_delivery.
        Before the fix, this exception propagated straight out of
        _process_channel, past handle_notification_event's own catch-all —
        the offset still committed, and the row was stuck at "sending"
        forever with no failed record and no automatic recovery."""
        row = (1, {"value": "x", "delivery": "in_progress"})
        db = object()
        auth_db = object()
        with patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=row),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send",
            AsyncMock(return_value=True),
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _auth_session_scope_stub(auth_db),
        ), patch(
            "consumers.notifications_consumer.handler.delivery.deliver",
            AsyncMock(side_effect=RuntimeError("boom")),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.mark_delivery", AsyncMock()
        ) as mark:
            # Must not raise — handler.py settles the row itself rather than
            # letting the exception propagate.
            await _process_channel(db, _cfg(), _envelope(), "EMAIL")

        mark.assert_awaited_once_with(db, row_id=1, delivery="failed")


class TestHandleNotificationEventEmptyRecipients:
    """handle_notification_event must NOT gate on an empty recipients list
    itself. The producer already committed the ledger row as "in_progress"
    before ever publishing (check_and_record_threshold /
    check_and_record_exhaustion), and main.py commits the Kafka offset once
    this function returns regardless of what it did. An early return on
    ``not envelope["recipients"]`` used to skip _process_channel entirely,
    leaving that row wedged at "in_progress" forever with no failed record
    and no automatic recovery — exactly the bug test_delivery_raising_
    still_settles_failed above exists to prevent for a raise, but for this
    path nothing settled the row at all, not even to "failed".

    Empty recipients must instead flow all the way through to
    delivery.deliver()'s real "no_recipients" outcome (not stubbed — this
    exercises the actual empty-`people`-list branch), which
    _process_channel already settles as "failed"."""

    async def test_empty_recipients_settles_the_ledger_row_to_failed(self):
        db = object()
        row = (1, {"value": "x", "delivery": "in_progress"})
        msg = object()  # never actually parsed — _parse_envelope is stubbed below

        with patch(
            "consumers.notifications_consumer.handler._parse_envelope",
            lambda _msg: _envelope(recipients=[]),
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _auth_session_scope_stub(db),
        ), patch(
            "consumers.notifications_consumer.handler.get_config",
            AsyncMock(return_value=_cfg(channels=["EMAIL"])),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.fetch_row",
            AsyncMock(return_value=row),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.claim_send",
            AsyncMock(return_value=True),
        ), patch(
            "consumers.notifications_consumer.handler.ledger.mark_delivery", AsyncMock()
        ) as mark:
            # delivery.deliver itself is deliberately NOT patched — with
            # recipients=[], it builds an empty `people` list and returns
            # "no_recipients" on its own, the real behavior this test pins.
            await handle_notification_event(msg)

        mark.assert_awaited_once_with(db, row_id=1, delivery="failed")

    async def test_empty_recipients_reaches_process_channel_for_every_configured_channel(self):
        """A lighter-weight companion to the settlement test above: pins
        that _process_channel is actually invoked (the early return this
        PR removes would have skipped it) for each of the catalog row's
        configured channels, not just EMAIL."""
        process_channel = AsyncMock()
        envelope = _envelope(recipients=[])
        cfg = _cfg(channels=["EMAIL", "SLACK"])

        with patch(
            "consumers.notifications_consumer.handler._parse_envelope",
            lambda _msg: envelope,
        ), patch(
            "consumers.notifications_consumer.handler.session_scope",
            _auth_session_scope_stub(object()),
        ), patch(
            "consumers.notifications_consumer.handler.get_config",
            AsyncMock(return_value=cfg),
        ), patch(
            "consumers.notifications_consumer.handler._process_channel", process_channel,
        ):
            await handle_notification_event(object())

        assert process_channel.await_count == 2
        called_channels = {call.args[3] for call in process_channel.await_args_list}
        assert called_channels == {"EMAIL", "SLACK"}
        for call in process_channel.await_args_list:
            assert call.args[2] is envelope
