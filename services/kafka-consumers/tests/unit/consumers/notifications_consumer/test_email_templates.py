"""consumers/notifications_consumer/email_templates.py — ported from
services/platform-core-service/app/services/notification_alert_email_templates.py
(PR #1557). This suite mirrors that module's own test file
(test_notification_alert_email_templates.py) closely on purpose: same
renderers, same enums, same templates — pinning that the port didn't
silently change behaviour along the way.
"""
from __future__ import annotations

import pytest

from consumers.notifications_consumer import email_templates as templates
from consumers.notifications_consumer.config import get_settings


@pytest.fixture(autouse=True)
def _no_portal_url(monkeypatch):
    """Default to no PORTAL_URL so the plain-text fallback wording is asserted
    consistently; test_portal_link_uses_configured_url overrides this."""
    monkeypatch.setattr(get_settings(), "PORTAL_URL", None)


# Each entry: (render fn, kwargs, substrings expected in BOTH html_body and text_body)
CASES = [
    (
        templates.render_notification_email,
        dict(
            to="a@b.com", recipient_name="Priya", notification_name="Budget Assigned",
            institution_name="Acme Bank", notification_headline="A Budget has been assigned to Acme Bank.",
            notification_details=["Budget: INR 50,000"],
        ),
        ["Priya", "Acme Bank", "A Budget has been assigned to Acme Bank.", "Budget: INR 50,000"],
    ),
    (
        templates.render_alert_email,
        dict(
            to="a@b.com", recipient_name="Priya", alert_name="Quota Usage",
            institution_name="Acme Bank", alert_datetime="2026-09-10 14:30 UTC",
            threshold="80", current_value="82.4",
        ),
        ["Priya", "Acme Bank", "80%", "82.4"],
    ),
    (
        templates.render_tier_assigned_email,
        dict(
            to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
            tier_name="Gold", tier_description="High-volume tier",
            quota_lines=["ASR: 10,000 req/mo", "MT: 5,000 req/mo"],
        ),
        ["Gold", "High-volume tier", "ASR: 10,000 req/mo", "MT: 5,000 req/mo"],
    ),
    (
        templates.render_budget_assigned_email,
        dict(to="a@b.com", recipient_name="Priya", institution_name="Acme Bank", currency="INR", budget_amount="500000"),
        ["Acme Bank", "INR", "500000"],
    ),
    (
        templates.render_tier_reassigned_email,
        dict(
            to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
            current_tier_name="Gold", new_tier_name="Platinum", new_tier_description="Premium tier",
            quota_lines=["ASR: 20,000 req/mo"],
        ),
        ["Gold", "Platinum", "Premium tier", "ASR: 20,000 req/mo"],
    ),
    (
        templates.render_quota_limit_updated_email,
        dict(
            to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
            tier_name="Gold", changes=["ASR: changed from 10,000 to 15,000"], effective_date="2026-09-10",
        ),
        ["Gold", "ASR: changed from 10,000 to 15,000", "2026-09-10"],
    ),
    (
        templates.render_budget_revised_email,
        dict(
            to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
            currency="INR", previous_value="500000", new_value="750000", effective_date="2026-09-10",
        ),
        ["INR 500000", "INR 750000", "2026-09-10"],
    ),
    (
        templates.render_quota_exhausted_email,
        dict(
            to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
            tier_name="Gold", exhausted_lines=["ASR: Quota Limit 10,000, Resets on 2026-10-01"],
        ),
        ["Gold", "ASR: Quota Limit 10,000, Resets on 2026-10-01"],
    ),
    (
        templates.render_budget_exhausted_email,
        dict(to="a@b.com", recipient_name="Priya", institution_name="Acme Bank", currency="INR", budget_amount="500000"),
        ["Acme Bank", "INR", "500000"],
    ),
    (
        templates.render_quota_threshold_alert_email,
        dict(
            to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
            threshold="80", alert_datetime="2026-09-10 14:30 UTC", current_value="81",
        ),
        ["Acme Bank", "80%", "81"],
    ),
    (
        templates.render_budget_threshold_alert_email,
        dict(
            to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
            threshold="80", alert_datetime="2026-09-10 14:30 UTC", current_value="81",
        ),
        ["Acme Bank", "80%", "81"],
    ),
]


@pytest.mark.parametrize("render_fn,kwargs,expected_substrings", CASES, ids=[c[0].__name__ for c in CASES])
def test_render_produces_populated_email(render_fn, kwargs, expected_substrings):
    message = render_fn(**kwargs)

    assert message.to == "a@b.com"
    assert message.subject.strip()
    assert message.html_body.strip()
    assert message.text_body.strip()

    for substring in expected_substrings:
        assert substring in message.html_body, f"{substring!r} missing from html_body"
        assert substring in message.text_body, f"{substring!r} missing from text_body"


@pytest.mark.parametrize("notification_name", [n.value for n in templates.NotificationName])
def test_notification_subject_uses_enum_value(notification_name):
    """Renaming a NotificationName member should be the only place a subject-line
    change is needed — this pins the subject format to the enum's current values."""
    message = templates.render_notification_email(
        to="a@b.com", recipient_name="Priya", notification_name=notification_name,
        institution_name="Acme Bank", notification_headline="Headline.", notification_details=["Detail."],
    )
    assert message.subject == f"{notification_name} — Acme Bank"


@pytest.mark.parametrize("alert_name", [a.value for a in templates.AlertName])
def test_alert_subject_uses_enum_value(alert_name):
    message = templates.render_alert_email(
        to="a@b.com", recipient_name="Priya", alert_name=alert_name,
        institution_name="Acme Bank", alert_datetime="2026-09-10", threshold="80", current_value="81",
    )
    assert message.subject == f"{alert_name} at 80% — Acme Bank"


def test_portal_link_uses_configured_url(monkeypatch):
    monkeypatch.setattr(get_settings(), "PORTAL_URL", "https://portal.example.com")

    message = templates.render_budget_assigned_email(
        to="a@b.com", recipient_name="Priya", institution_name="Acme Bank", currency="INR", budget_amount="500000",
    )

    assert 'href="https://portal.example.com"' in message.html_body
    assert "https://portal.example.com" in message.text_body


def test_portal_link_falls_back_to_plain_text_when_unset():
    message = templates.render_budget_assigned_email(
        to="a@b.com", recipient_name="Priya", institution_name="Acme Bank", currency="INR", budget_amount="500000",
    )

    assert "Log in to the AI4I-Orchestrate Portal to view full details." in message.text_body
    assert "href=" not in message.text_body
