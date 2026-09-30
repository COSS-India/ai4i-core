"""consumers/notifications_consumer/failures.py — the row written to
notification_alert_failure_log for an undelivered event.

Runs the real ai4i_core.kafka FailureLogger against a fake session, so the
INSERT parameters asserted here are the ones Postgres would get.
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager

import pytest
from ai4i_core.kafka import FailureCode

from consumers.notifications_consumer import failures

EVENT_ID = "5f0c8a52-6c1e-4d1e-9a51-8f3d2a7e4b10"


class _Session:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, statement, params):
        self.rows.append(params)

    async def commit(self):
        pass


@pytest.fixture
def rows(monkeypatch):
    written = []

    @asynccontextmanager
    async def _scope(name=None):
        yield _Session(written)

    failures._failure_logger.cache_clear()
    monkeypatch.setattr(failures, "session_scope", _scope)
    monkeypatch.setenv("POD_NAME", "notifications-consumer-0")
    yield written
    failures._failure_logger.cache_clear()


async def test_row_carries_the_envelope_identity(rows):
    envelope = {
        "event_id": EVENT_ID,
        "event_name": "QUOTA_THRESHOLD",
        "tenant_id": 42,
        "subject": {"model_task_type": "asr", "billing_month": "2026-09"},
        "band": {"value": 80, "unit": "PERCENT"},
        "observed": {"value": 81.42, "unit": "PERCENT"},
    }

    await failures.record(
        envelope, FailureCode.EMAIL_SEND_FAILED, kafka_topic="notification.events",
        message="email reached 0 of 2 recipient(s)",
    )

    [row] = rows
    assert row["event_id"] == uuid.UUID(EVENT_ID)
    assert row["notification_name"] == "QUOTA_THRESHOLD"
    assert row["notification_id"] is None
    assert row["tenant_id"] == "42"
    assert json.loads(row["subject"]) == envelope["subject"]
    assert row["producer"] == "notifications-consumer"
    assert row["pod_name"] == "notifications-consumer-0"
    assert row["stage"] == "DELIVERY"
    assert row["error_code"] == "EMAIL_SEND_FAILED"
    assert row["error_message"] == "email reached 0 of 2 recipient(s)"
    detail = json.loads(row["error_detail"])
    assert detail["operation"] == "email_send"
    assert detail["kafka_topic"] == "notification.events"
    assert detail["band"] == envelope["band"]
    assert detail["observed"] == envelope["observed"]


async def test_unusable_envelope_fields_are_left_out(rows):
    await failures.record(
        {"event_id": "not-a-uuid", "subject": "x", "band": [80]},
        FailureCode.EMAIL_SEND_FAILED, kafka_topic="t", error=RuntimeError("boom"),
    )

    [row] = rows
    assert row["event_id"] is None
    assert row["notification_name"] == failures.UNKNOWN_NOTIFICATION
    assert row["subject"] is None
    assert row["error_message"] == "boom"
    detail = json.loads(row["error_detail"])
    assert detail["exception"] == "RuntimeError"
    assert detail["band"] is None


async def test_a_failed_write_does_not_raise(monkeypatch):
    @asynccontextmanager
    async def _down(name=None):
        raise ConnectionError("db down")
        yield

    failures._failure_logger.cache_clear()
    monkeypatch.setattr(failures, "session_scope", _down)
    try:
        await failures.record({"event_id": EVENT_ID}, FailureCode.EMAIL_SEND_FAILED, kafka_topic="t")
    finally:
        failures._failure_logger.cache_clear()


async def test_a_grouped_event_writes_one_row_per_service(rows):
    """12:27 — one email for asr, llm and tts fails to send: each service
    gets its row, instead of one row with an empty subject."""
    envelope = {
        "event_id": EVENT_ID,
        "event_name": "ERROR_RATE_5XX",
        "tenant_id": "PLATFORM",
        "subject": {},
        "subjects": [{"service_id": "asr-service"}, {"service_id": "llm-service"}, {"service_id": "tts-service"}],
        "band": {"value": 10, "unit": "PERCENT"},
    }

    await failures.record(
        envelope, FailureCode.EMAIL_SEND_FAILED, kafka_topic="notification.events",
        message="email reached 0 of 2 recipient(s)",
    )

    assert [json.loads(row["subject"]) for row in rows] == envelope["subjects"]
    assert {row["event_id"] for row in rows} == {uuid.UUID(EVENT_ID)}
    assert {row["error_code"] for row in rows} == {"EMAIL_SEND_FAILED"}


@pytest.mark.parametrize("subjects", [None, [], "asr-service", 7, ["asr-service"]])
async def test_unusable_subjects_fall_back_to_the_one_subject(rows, subjects):
    """Envelopes from before the list, or with a broken one, still write their single row."""
    await failures.record(
        {"event_id": EVENT_ID, "subject": {"service_id": "asr-service"}, "subjects": subjects},
        FailureCode.EMAIL_SEND_FAILED, kafka_topic="t",
    )

    [row] = rows
    assert json.loads(row["subject"]) == {"service_id": "asr-service"}
