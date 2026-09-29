"""consumers/notifications_consumer/handler.py — envelope -> emailer.send per
recipient; one failure row when the email reached no one.

emailer.send and failures.record are faked; nothing here touches a real
database, Kafka, Redis or SMTP.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from ai4i_core.kafka import FailureCode, Operation

from consumers.notifications_consumer import handler as h

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


async def _handle(payload, *, sent=(True, True), send_error=None):
    send = AsyncMock(side_effect=send_error or list(sent))
    record = AsyncMock()
    with patch.object(h.emailer, "send", send), patch.object(h.failures, "record", record):
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
    _, record = await _handle(_payload(), sent=(False, True))
    record.assert_not_awaited()


async def test_no_recipient_reached_is_recorded():
    payload = _payload()
    _, record = await _handle(payload, sent=(False, False))

    record.assert_awaited_once_with(
        payload, FailureCode.EMAIL_SEND_FAILED, kafka_topic=TOPIC, message="email reached 0 of 2 recipient(s)",
    )


@pytest.mark.parametrize("recipients", [[], None])
async def test_no_recipients_is_recorded(recipients):
    send, record = await _handle(_payload(recipients=recipients), sent=())

    send.assert_not_awaited()
    assert record.await_args.args[1] is FailureCode.EMAIL_SEND_FAILED
    assert record.await_args.kwargs["message"] == "email reached 0 of 0 recipient(s)"


@pytest.mark.parametrize("channels", [["SLACK"], [], None])
async def test_no_email_channel_is_recorded_without_sending(channels):
    send, record = await _handle(_payload(channels=channels))

    send.assert_not_awaited()
    assert record.await_args.args[1] is FailureCode.NO_SUPPORTED_CHANNEL


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
