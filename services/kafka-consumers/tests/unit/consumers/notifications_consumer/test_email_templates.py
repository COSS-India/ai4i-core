"""consumers/notifications_consumer/email_templates.py — the one generic
render_email function every event_name goes through.

No per-event renderers left to pin (see module docstring): this suite
covers the subject format, the blind positional mapping (details[0] ->
field_1, details[1] -> field_2, ...), that a short details array leaves the
remaining fields blank without erroring, and the portal-link fallback.
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


def test_render_produces_populated_email():
    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="TIER_CHANGED",
        tenant_name="Acme Bank", details=["Silver", "Gold", "Premium tier"],
    )

    assert message.to == "a@b.com"
    assert message.subject == "TIER_CHANGED — Acme Bank"
    assert message.html_body.strip()
    assert message.text_body.strip()
    for substring in ["Priya", "Silver", "Gold", "Premium tier"]:
        assert substring in message.html_body, f"{substring!r} missing from html_body"
        assert substring in message.text_body, f"{substring!r} missing from text_body"


def test_details_map_positionally_in_order_without_interpretation():
    """Blind mapping: details[0] -> field_1, details[1] -> field_2, etc. —
    whatever order the producer sends details in is the order they show up
    in the body, no relabeling or reordering."""
    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="QUOTA_LIMIT_UPDATED",
        tenant_name="Acme Bank", details=["first", "second", "third"],
    )

    html = message.html_body
    assert html.index("first") < html.index("second") < html.index("third")


def test_fewer_details_than_field_slots_leaves_the_rest_blank():
    """An event_name that only ever sends 2 values must not render 4 empty
    paragraphs for the unused trailing slots."""
    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="BUDGET_ASSIGNED",
        tenant_name="Acme Bank", details=["INR", "500000"],
    )

    assert "INR" in message.html_body
    assert "500000" in message.html_body
    # No empty <p> line left over from an unfilled field slot.
    assert '<p style="margin:0 0 4px 0;"></p>' not in message.html_body


def test_more_details_than_field_slots_are_silently_dropped():
    """Only _FIELD_COUNT positions exist — extra values past that are not
    rendered anywhere (and don't raise); this module doesn't verify count."""
    details = [f"value-{i}" for i in range(templates._FIELD_COUNT + 2)]
    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="TIER_CHANGED",
        tenant_name="Acme Bank", details=details,
    )

    for i in range(templates._FIELD_COUNT):
        assert f"value-{i}" in message.html_body
    for i in range(templates._FIELD_COUNT, len(details)):
        assert f"value-{i}" not in message.html_body


def test_empty_details_renders_without_error():
    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="BUDGET_EXHAUSTED",
        tenant_name="Acme Bank", details=[],
    )
    assert message.subject == "BUDGET_EXHAUSTED — Acme Bank"
    assert message.html_body.strip()


def test_subject_uses_event_name_and_tenant_name_verbatim():
    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="anything_at_all",
        tenant_name="Some Tenant", details=[],
    )
    assert message.subject == "anything_at_all — Some Tenant"


def test_portal_link_uses_configured_url(monkeypatch):
    monkeypatch.setattr(get_settings(), "PORTAL_URL", "https://portal.example.com")

    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="BUDGET_ASSIGNED",
        tenant_name="Acme Bank", details=["INR 500000"],
    )

    assert 'href="https://portal.example.com"' in message.html_body
    assert "https://portal.example.com" in message.text_body


def test_portal_link_falls_back_to_plain_text_when_unset():
    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="BUDGET_ASSIGNED",
        tenant_name="Acme Bank", details=["INR 500000"],
    )

    assert "Log in to the AI4I-Orchestrate Portal to view full details." in message.text_body
    assert "href=" not in message.text_body


@pytest.mark.parametrize("event_name", sorted(templates._ALERT_EVENTS))
class TestAlertEventsUseTheAlertTemplate:
    """QUOTA_THRESHOLD/BUDGET_THRESHOLD are the only two events that render
    through alert.html/.txt instead of notification.html/.txt — same split
    as the original design. field_1/field_2/field_3 are still a blind
    positional mapping (threshold/alert_datetime/current_value, in that
    order), not a named/validated one."""

    def test_subject_includes_percent_sign(self, event_name):
        message = templates.render_email(
            to="a@b.com", recipient_name="Priya", event_name=event_name,
            tenant_name="Acme Bank", details=["80", "2026-09-10 14:30 UTC", "82.4"],
        )
        assert message.subject == f"{event_name} at 80% — Acme Bank"

    def test_body_contains_threshold_datetime_and_current_value_in_order(self, event_name):
        message = templates.render_email(
            to="a@b.com", recipient_name="Priya", event_name=event_name,
            tenant_name="Acme Bank", details=["80", "2026-09-10 14:30 UTC", "82.4"],
        )
        for substring in ["Priya", "Acme Bank", "80%", "2026-09-10 14:30 UTC", "82.4"]:
            assert substring in message.html_body, f"{substring!r} missing from html_body"
            assert substring in message.text_body, f"{substring!r} missing from text_body"


def test_non_alert_event_does_not_use_percent_subject_format():
    message = templates.render_email(
        to="a@b.com", recipient_name="Priya", event_name="TIER_CHANGED",
        tenant_name="Acme Bank", details=["80", "2026-09-10", "82.4"],
    )
    assert message.subject == "TIER_CHANGED — Acme Bank"
    assert "%" not in message.subject
