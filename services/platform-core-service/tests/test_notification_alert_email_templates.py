"""Tests for app/services/notification_alert_email_templates.py.

Calls every render_*_email() function once and asserts it produces a
non-empty EmailMessage with the right values substituted — closing the gap
flagged in code review: nothing in the repo previously rendered any of these
templates, so a context key that doesn't match its Jinja template (StrictUndefined)
would only ever surface as an email that silently never arrives (enqueue_email
catches the render error, logs it, and returns).

Import note
-----------
conftest.py stubs ``ai4i_core`` with a bare module exposing only
``.exceptions``, so tests that don't need email can run without pulling in
the heavier ai4i_core.bootstrap machinery. This module needs the REAL
ai4i_core.email (EmailMessage, TemplateRenderer) to actually exercise the
Jinja templates end-to-end, so we evict that stub, force a real import of
the module under test, then restore the stub so later test files that rely
on it are unaffected. app.services.notification_alert_email_templates keeps
its own already-bound EmailMessage/TemplateRenderer references regardless of
what sys.modules holds afterward.
"""

import sys

import pytest

_saved_ai4i_core = sys.modules.pop("ai4i_core", None)
_saved_ai4i_core_exceptions = sys.modules.pop("ai4i_core.exceptions", None)
sys.modules.pop("ai4i_core.email", None)

import app.services.notification_alert_email_templates as templates  # noqa: E402
from app.core.config import settings  # noqa: E402

if _saved_ai4i_core is not None:
    sys.modules["ai4i_core"] = _saved_ai4i_core
if _saved_ai4i_core_exceptions is not None:
    sys.modules["ai4i_core.exceptions"] = _saved_ai4i_core_exceptions


@pytest.fixture(autouse=True)
def _no_portal_url(monkeypatch):
    """Default to no PORTAL_URL so the plain-text fallback wording is asserted
    consistently; test_portal_link_uses_configured_url overrides this."""
    monkeypatch.setattr(settings, "portal_url", None)


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
            institution_name="Acme Bank", alert_datetime="2026-09-10 14:30 IST",
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
            rate_limit_value="1000", effective_from="2026-09-10", effective_to="2027-09-09",
        ),
        ["Gold", "High-volume tier", "ASR: 10,000 req/mo", "MT: 5,000 req/mo", "1000", "2026-09-10", "2027-09-09"],
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
            quota_lines=["ASR: 20,000 req/mo"], new_rate_limit_value="2000",
            effective_from="2026-09-10", effective_to="2027-09-09",
        ),
        ["Gold", "Platinum", "Premium tier", "ASR: 20,000 req/mo", "2000"],
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
            threshold="80", alert_datetime="2026-09-10 14:30 IST", current_value="81",
        ),
        ["Acme Bank", "80%", "81"],
    ),
    (
        templates.render_budget_threshold_alert_email,
        dict(
            to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
            threshold="80", alert_datetime="2026-09-10 14:30 IST", current_value="81",
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


@pytest.mark.parametrize(
    "notification_name",
    [n.value for n in templates.NotificationName],
)
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
    monkeypatch.setattr(settings, "portal_url", "https://portal.example.com")

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
