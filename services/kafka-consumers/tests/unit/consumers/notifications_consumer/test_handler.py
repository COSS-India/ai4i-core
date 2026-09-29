"""consumers/notifications_consumer/handler.py — the event_id claim, then
envelope -> emailer.send per recipient; one failure row when the email
reached no one.

emailer.send, failures.record and the Redis client are faked; nothing here
touches a real database, Kafka, Redis or SMTP.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from ai4i_core.email.exceptions import EmailDeliveryError
from ai4i_core.kafka import FailureCode, Operation
from jinja2 import UndefinedError

from consumers.notifications_consumer import handler as h
from consumers.notifications_consumer.config import Constants

TOPIC = "notification.events"


def _payload(**overrides) -> dict:
    base = {
        "schema_version": 2,
        "event_id": "5f0c8a52-6c1e-4d1e-9a51-8f3d2a7e4b10",
        "event_name": "QUOTA_THRESHOLD",
        "notification_type": "ALERT",
        "tenant_id": "42",
        "tenant_name": "IIT Madras",
        "subject": {"billing_month": "2026-09", "model_task_type": "asr"},
        "occurred_at": "2026-09-28T10:15:00.000+00:00",
        "channels": ["EMAIL"],
        "severity": "WARNING",
        "band": {"value": 80, "unit": "PERCENT"},
        "observed": {"value": 81.42, "unit": "PERCENT"},
        "details": ["80", "28 Sep 2026, 03:45 PM IST", "81% (ASR)"],
        "recipients": [
            {"email": "priya@iitm.example.org", "name": "Priya Raman"},
            {"email": "ops@ai4i.example.org", "name": "Arun Kumar"},
        ],
    }
    base.update(overrides)
    return base


def _msg(payload) -> SimpleNamespace:
    raw = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
    return SimpleNamespace(value=lambda: raw, topic=lambda: TOPIC, partition=lambda: 0, offset=lambda: 1)


class _Redis:
    def __init__(self, won=True, raises=False):
        self.won, self.raises, self.calls = won, raises, []

    async def set(self, key, value, nx=False, ex=None):
        self.calls.append((key, nx, ex))
        if self.raises:
            raise ConnectionError("redis down")
        return self.won


def _outcomes(values):
    """emailer.send results in order: None = sent, an exception = why not.
    Returned, not raised — AsyncMock(side_effect=[exc]) would raise it."""
    remaining = iter(values)

    async def _send(**kwargs):
        return next(remaining)
    return _send


async def _handle(payload, *, sent=(None, None), send_error=None, redis=None):
    send = AsyncMock(side_effect=send_error or _outcomes(sent))
    record = AsyncMock()
    redis = redis or _Redis()
    with patch.object(h.emailer, "send", send), patch.object(h.failures, "record", record), patch.object(
        h, "get_redis_client", lambda: redis
    ):
        await h.handle_notification_event(_msg(payload))
    return send, record


async def test_each_recipient_gets_the_envelope_fields_verbatim():
    payload = _payload()
    send, record = await _handle(payload)

    assert [call.kwargs for call in send.await_args_list] == [
        dict(recipient=r, event_name="QUOTA_THRESHOLD", tenant_name="IIT Madras", details=payload["details"])
        for r in payload["recipients"]
    ]
    record.assert_not_awaited()


async def test_one_recipient_reached_counts_as_delivered():
    _, record = await _handle(_payload(), sent=(EmailDeliveryError("SMTP 554"), None))
    record.assert_not_awaited()


async def test_no_recipient_reached_records_the_first_error():
    payload = _payload()
    render_error = UndefinedError("list object has no element 3")
    _, record = await _handle(payload, sent=(render_error, EmailDeliveryError("SMTP 554")))

    record.assert_awaited_once_with(
        payload, FailureCode.EMAIL_SEND_FAILED, kafka_topic=TOPIC,
        message="email reached 0 of 2 recipient(s); first error: UndefinedError: list object has no element 3",
        error=render_error,
    )


async def test_an_error_without_text_is_named_by_type():
    timeout = TimeoutError()
    _, record = await _handle(_payload(), sent=(timeout, timeout))

    assert record.await_args.kwargs["error"] is timeout
    assert record.await_args.kwargs["message"] == "email reached 0 of 2 recipient(s); first error: TimeoutError"


@pytest.mark.parametrize("recipients", [[], None])
async def test_no_recipients_is_recorded(recipients):
    send, record = await _handle(_payload(recipients=recipients), sent=())

    send.assert_not_awaited()
    assert record.await_args.args[1] is FailureCode.EMAIL_SEND_FAILED
    assert record.await_args.kwargs["message"] == "email reached 0 of 0 recipient(s)"
    assert record.await_args.kwargs["error"] is None


@pytest.mark.parametrize("channels", [["SLACK"], [], None])
async def test_no_email_channel_is_recorded_without_sending(channels):
    send, record = await _handle(_payload(channels=channels))

    send.assert_not_awaited()
    assert record.await_args.args[1] is FailureCode.NO_SUPPORTED_CHANNEL
    assert record.await_args.kwargs["error"] is None


async def test_missing_details_are_sent_as_an_empty_list():
    send, _ = await _handle(_payload(details=None))
    assert send.await_args.kwargs["details"] == []


@pytest.mark.parametrize("raw", [b"{not json", b"[1, 2]", b'"text"', None])
async def test_malformed_message_is_recorded(raw):
    send, record = await _handle(raw)

    send.assert_not_awaited()
    assert record.await_args.args[:2] == ({}, FailureCode.INVALID_ENVELOPE)
    assert record.await_args.kwargs["operation"] is Operation.VALIDATE
    assert isinstance(record.await_args.kwargs["error"], (TypeError, ValueError))


async def test_delivery_raising_is_recorded_not_propagated():
    payload = _payload(recipients=42)  # not iterable
    _, record = await _handle(payload)

    assert record.await_args.args == (payload, FailureCode.EMAIL_SEND_FAILED)
    assert isinstance(record.await_args.kwargs["error"], TypeError)


class TestEventIdClaim:
    async def test_first_delivery_claims_the_event_id_before_sending(self):
        redis = _Redis(won=True)
        send, _ = await _handle(_payload(), redis=redis)

        assert redis.calls == [(
            f"{Constants.DELIVERY_CLAIM_KEY_PREFIX}5f0c8a52-6c1e-4d1e-9a51-8f3d2a7e4b10",
            True, Constants.DELIVERY_CLAIM_TTL_SECONDS,
        )]
        assert send.await_count == 2

    async def test_redelivery_of_a_claimed_event_is_not_sent_or_recorded(self):
        send, record = await _handle(_payload(), redis=_Redis(won=False))

        send.assert_not_awaited()
        record.assert_not_awaited()

    async def test_redis_down_still_delivers(self):
        send, record = await _handle(_payload(), redis=_Redis(raises=True))

        assert send.await_count == 2
        record.assert_not_awaited()

    @pytest.mark.parametrize("event_id", [None, ""])
    async def test_no_event_id_delivers_without_a_claim(self, event_id):
        redis = _Redis()
        send, _ = await _handle(_payload(event_id=event_id), redis=redis)

        assert redis.calls == []
        assert send.await_count == 2

    async def test_malformed_message_takes_no_claim(self):
        redis = _Redis()
        await _handle(b"{not json", redis=redis)

        assert redis.calls == []
