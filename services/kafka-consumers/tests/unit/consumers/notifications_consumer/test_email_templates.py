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
from consumers.notifications_consumer.config import DEFAULT_PLATFORM_NAME, get_settings


@pytest.fixture(autouse=True)
def _no_portal_url(monkeypatch):
    """Default to no PORTAL_URL so the plain-text fallback wording is asserted
    consistently; test_portal_link_uses_configured_url overrides this."""
    monkeypatch.setattr(get_settings(), "PORTAL_URL", None)


@pytest.fixture(autouse=True)
def _default_branding(monkeypatch):
    """Pin the default brand so a local .env's PLATFORM_NAME / ADOPTER_LOGO_URL
    can't change what these tests assert; the branding tests below override it."""
    monkeypatch.setattr(get_settings(), "PLATFORM_NAME", DEFAULT_PLATFORM_NAME)
    monkeypatch.setattr(get_settings(), "ADOPTER_LOGO_URL", None)


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
    (
        templates.render_monitoring_alert_email,
        dict(
            to="a@b.com", recipient_name="Priya", alert=templates.MonitoringAlertName.ERROR_RATE_4XX,
            threshold="5", alert_datetime="2026-09-28 10:00 UTC", current_value="6.2",
        ),
        ["Priya", "4xx Error Rate", "5%", "6.2%", "2026-09-28 10:00 UTC"],
    ),
    (
        templates.render_monitoring_alert_email,
        dict(
            to="a@b.com", recipient_name="Priya", alert=templates.MonitoringAlertName.LATENCY_P95,
            threshold="5", alert_datetime="2026-09-28 10:00 UTC", current_value="7.3",
        ),
        ["Priya", "P95 Latency", "5s", "7.3s", "2026-09-28 10:00 UTC"],
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


@pytest.mark.parametrize("alert", list(templates.MonitoringAlertName), ids=lambda a: a.name)
def test_monitoring_alert_subject_uses_enum_value_and_unit(alert):
    """Every MonitoringAlertName has a unit, and the subject carries the
    alert's own unit — never the metering "%" by default, never an institution."""
    unit = templates.MONITORING_ALERT_UNITS[alert]
    message = templates.render_monitoring_alert_email(
        to="a@b.com", recipient_name="Priya", alert=alert,
        threshold="10", alert_datetime="2026-09-28", current_value="11",
    )
    assert message.subject == f"{alert.value} — Threshold 10{unit}"
    assert unit == ("%" if alert.name.startswith("ERROR_RATE") else "s")
    assert "Acme Bank" not in message.subject


def test_monitoring_alert_portal_link_uses_configured_url(monkeypatch):
    monkeypatch.setattr(get_settings(), "PORTAL_URL", "https://portal.example.com")

    message = templates.render_monitoring_alert_email(
        to="a@b.com", recipient_name="Priya", alert=templates.MonitoringAlertName.LATENCY_P50,
        threshold="1", alert_datetime="2026-09-28", current_value="1.4",
    )

    assert 'href="https://portal.example.com"' in message.html_body
    assert "https://portal.example.com" in message.text_body


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

    assert f"Log in to the {DEFAULT_PLATFORM_NAME} Portal to view full details." in message.text_body
    assert "href=" not in message.text_body


# ── Branding (PLATFORM_NAME / ADOPTER_LOGO_URL — same pair as auth-service) ──

_BRANDING_RENDERERS = [
    lambda: templates.render_budget_assigned_email(
        to="a@b.com", recipient_name="Priya", institution_name="Acme Bank", currency="INR", budget_amount="500000",
    ),
    lambda: templates.render_quota_threshold_alert_email(
        to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
        threshold="80", alert_datetime="2026-09-10", current_value="81",
    ),
    lambda: templates.render_monitoring_alert_email(
        to="a@b.com", recipient_name="Priya", alert=templates.MonitoringAlertName.LATENCY_P95,
        threshold="5", alert_datetime="2026-09-28", current_value="7.3",
    ),
]


@pytest.mark.parametrize("render", _BRANDING_RENDERERS, ids=["notification", "alert", "monitoring_alert"])
def test_platform_name_comes_from_settings(monkeypatch, render):
    monkeypatch.setattr(get_settings(), "PLATFORM_NAME", "Custom Brand")

    message = render()

    for body in (message.html_body, message.text_body):
        assert "Log in to the Custom Brand Portal to view full details." in body
        assert "Custom Brand Team" in body
        assert DEFAULT_PLATFORM_NAME not in body
    assert "&copy; Custom Brand" in message.html_body


def test_blank_platform_name_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(get_settings(), "PLATFORM_NAME", "   ")

    message = _BRANDING_RENDERERS[2]()

    assert f"{DEFAULT_PLATFORM_NAME} Team" in message.text_body


def test_logo_url_replaces_text_brand_mark_in_header(monkeypatch):
    monkeypatch.setattr(get_settings(), "ADOPTER_LOGO_URL", "https://cdn.example.com/logo.png")

    message = _BRANDING_RENDERERS[2]()

    assert f'<img src="https://cdn.example.com/logo.png" alt="{DEFAULT_PLATFORM_NAME}"' in message.html_body


def test_relative_logo_url_is_ignored(monkeypatch):
    monkeypatch.setattr(get_settings(), "ADOPTER_LOGO_URL", "/logo.png")

    message = _BRANDING_RENDERERS[2]()

    assert "<img" not in message.html_body


class TestResolveSmtpFromName:
    """EMAIL_FROM_NAME stays independent of PLATFORM_NAME; it only inherits it when blank."""

    def test_keeps_explicit_from_name(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "PLATFORM_NAME", DEFAULT_PLATFORM_NAME)
        assert get_settings().resolve_smtp_from_name("COSS Support") == "COSS Support"

    def test_inherits_platform_name_when_blank(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "PLATFORM_NAME", "Custom Brand")
        assert get_settings().resolve_smtp_from_name("") == "Custom Brand"
        assert get_settings().resolve_smtp_from_name("   ") == "Custom Brand"
