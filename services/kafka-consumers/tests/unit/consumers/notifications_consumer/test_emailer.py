"""consumers/notifications_consumer/emailer.py — send() renders through
email_templates.render_email and returns None on success, else the
exception that stopped it; it never raises.

The EmailClient is faked; nothing here reaches SMTP.
"""
from __future__ import annotations

import asyncio

import pytest
from ai4i_core.email.exceptions import EmailDeliveryError
from jinja2 import TemplateNotFound, UndefinedError

from consumers.notifications_consumer import emailer

RECIPIENT = {"email": "a@b.com", "name": "Priya"}


class _Client:
    """EmailClient.send: returns on success, raises the provider's error."""

    def __init__(self, error=None, delay_s=0.0):
        self.error, self.delay_s, self.sent = error, delay_s, []

    async def send(self, message):
        self.sent.append(message)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error


@pytest.fixture
def client(monkeypatch):
    fake = _Client()
    monkeypatch.setattr(emailer, "_client", lambda: fake)
    monkeypatch.setattr(emailer, "_send_deadline_s", lambda: 1.0)
    return fake


async def _send(recipient=RECIPIENT, event_name="BUDGET_ASSIGNED", details=("INR", "50000")):
    return await emailer.send(recipient=recipient, event_name=event_name, tenant_name="IIT Madras", details=list(details))


async def test_confirmed_send_returns_none(client):
    assert await _send() is None
    [message] = client.sent
    assert message.to == "a@b.com"
    assert message.subject == "Budget Assigned — IIT Madras"
    assert "Dear Priya," in message.text_body


async def test_monitoring_alert_send(client):
    assert await _send(event_name="LATENCY_P95", details=["5", "2026-09-28 10:00 IST", "7.3"]) is None
    [message] = client.sent
    assert message.subject == "P95 Latency — Threshold 5s"
    for body in (message.html_body, message.text_body):
        assert "Current Value: 7.3s" in body
        assert "IIT Madras" not in body


async def test_provider_failure_returns_the_provider_error(client):
    client.error = EmailDeliveryError("SMTP 554 rejected")
    assert await _send() is client.error


async def test_render_failure_returns_undefined_error_without_sending(client):
    error = await _send(details=["INR"])
    assert isinstance(error, UndefinedError)
    assert client.sent == []


async def test_unknown_event_returns_template_not_found_without_sending(client):
    assert isinstance(await _send(event_name="NOT_AN_EVENT"), TemplateNotFound)
    assert client.sent == []


@pytest.mark.parametrize("recipient,error_type", [
    ({"name": "No Email"}, KeyError), ("a@b.com", TypeError), (None, TypeError),
])
async def test_malformed_recipient_returns_the_error(client, recipient, error_type):
    assert isinstance(await _send(recipient=recipient), error_type)
    assert client.sent == []


async def test_send_past_the_deadline_returns_timeout_error(client, monkeypatch):
    client.delay_s = 1.0
    monkeypatch.setattr(emailer, "_send_deadline_s", lambda: 0.01)
    assert isinstance(await _send(), TimeoutError)
