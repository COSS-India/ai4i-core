"""consumers/notifications_consumer/emailer.py — send() renders through
email_templates.render_email and reports the outcome; it never raises.

The EmailClient is faked; nothing here reaches SMTP.
"""
from __future__ import annotations

import asyncio

import pytest

from consumers.notifications_consumer import emailer

RECIPIENT = {"email": "a@b.com", "name": "Priya"}


class _Client:
    def __init__(self, result=True, delay_s=0.0):
        self.result, self.delay_s, self.sent = result, delay_s, []

    async def send_safe(self, message):
        self.sent.append(message)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return self.result


@pytest.fixture
def client(monkeypatch):
    fake = _Client()
    monkeypatch.setattr(emailer, "_client", lambda: fake)
    monkeypatch.setattr(emailer, "_send_deadline_s", lambda: 1.0)
    return fake


async def _send(recipient=RECIPIENT, event_name="BUDGET_ASSIGNED", details=("INR", "50000")):
    return await emailer.send(recipient=recipient, event_name=event_name, tenant_name="IIT Madras", details=list(details))


async def test_confirmed_send_returns_true(client):
    assert await _send() is True
    [message] = client.sent
    assert message.to == "a@b.com"
    assert message.subject == "Budget Assigned — IIT Madras"
    assert "Dear Priya," in message.text_body


async def test_monitoring_alert_send(client):
    assert await _send(event_name="LATENCY_P95", details=["5", "2026-09-28 10:00 IST", "7.3"]) is True
    [message] = client.sent
    assert message.subject == "P95 Latency — Threshold 5s"
    for body in (message.html_body, message.text_body):
        assert "Current Value: 7.3s" in body
        assert "IIT Madras" not in body


async def test_provider_failure_returns_false(client):
    client.result = False
    assert await _send() is False


async def test_render_failure_returns_false_without_sending(client):
    assert await _send(details=["INR"]) is False
    assert client.sent == []


async def test_unknown_event_returns_false_without_sending(client):
    assert await _send(event_name="NOT_AN_EVENT") is False
    assert client.sent == []


@pytest.mark.parametrize("recipient", [{"name": "No Email"}, "a@b.com", None])
async def test_malformed_recipient_returns_false(client, recipient):
    assert await _send(recipient=recipient) is False
    assert client.sent == []


async def test_send_past_the_deadline_returns_false(client, monkeypatch):
    client.delay_s = 1.0
    monkeypatch.setattr(emailer, "_send_deadline_s", lambda: 0.01)
    assert await _send() is False
