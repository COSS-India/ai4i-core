"""consumers/notifications_consumer/email_templates.py — the one
render_email() and the per-event templates/emails/events/<event_name>.j2
files it picks up by event_name.

The wording pinned here is the Reference Email Template set (PR #1557) the
per-event renderer functions used to produce; the templates reproduce it
byte for byte.
"""
from __future__ import annotations

import pytest
from ai4i_core.kafka import NotificationName
from jinja2 import TemplateNotFound, UndefinedError

from consumers.notifications_consumer import email_templates as templates
from consumers.notifications_consumer.config import get_settings

TENANT = "IIT Madras"
WHEN = "28 Sep 2026, 03:45 PM IST"


@pytest.fixture(autouse=True)
def _no_portal_url(monkeypatch):
    """Default to no PORTAL_URL so the plain-text fallback wording is asserted
    consistently; the portal-link tests override this."""
    monkeypatch.setattr(get_settings(), "PORTAL_URL", None)


def _render(event_name, details, *, tenant_name=TENANT, recipient_name="Priya"):
    return templates.render_email(
        to="a@b.com", recipient_name=recipient_name, event_name=event_name,
        tenant_name=tenant_name, details=details,
    )


# (event_name, details, subject, substrings expected in BOTH html and text)
CASES = [
    (
        "TIER_ASSIGNED", ["Gold", "High-volume tier", ["ASR: 10,000 req/mo", "NMT: 5,000 req/mo"]],
        f"Tier Assigned — {TENANT}",
        [f"A Tier has been assigned to {TENANT}.", "Tier: Gold", "Description: High-volume tier",
         "Quota Limits:", "ASR: 10,000 req/mo", "NMT: 5,000 req/mo"],
    ),
    (
        "TIER_CHANGED", ["Silver", "Gold", "High-volume tier", ["ASR: 10,000 req/mo"]],
        f"Tier Reassignment — {TENANT}",
        [f"The Tier for {TENANT} has been reassigned.", "Current Tier: Silver → New Tier: Gold",
         "New Tier Description: High-volume tier", "New Tier Quota Limits:", "ASR: 10,000 req/mo"],
    ),
    (
        "BUDGET_ASSIGNED", ["INR", "50000"],
        f"Budget Assigned — {TENANT}",
        [f"A Budget has been assigned to {TENANT}.", "Budget: INR 50000"],
    ),
    (
        "BUDGET_UPDATED", ["INR", "50000", "75000", "2026-10-01"],
        f"Budget Revised — {TENANT}",
        ["Budget changed from INR 50000 to INR 75000", "Effective Date: 2026-10-01"],
    ),
    (
        "QUOTA_LIMIT_UPDATED", ["Gold", ["ASR: changed from 10,000 to 15,000"], "2026-10-01"],
        f"Quota Limit Updated — {TENANT}",
        ["Tier: Gold", "ASR: changed from 10,000 to 15,000", "Effective Date: 2026-10-01"],
    ),
    (
        "QUOTA_EXHAUSTED", ["Gold", ["ASR: Quota Limit 10,000, Resets on 2026-10-01"]],
        f"Quota Exhausted — {TENANT}",
        [f"The Quota for {TENANT} has been fully consumed.", "Tier: Gold",
         "ASR: Quota Limit 10,000, Resets on 2026-10-01"],
    ),
    (
        "BUDGET_EXHAUSTED", ["INR", "50000.00"],
        f"Budget Exhausted — {TENANT}",
        [f"The Budget for {TENANT} has been fully consumed.", "Budget: INR 50000.00"],
    ),
    (
        "QUOTA_THRESHOLD", ["80", WHEN, "81% (ASR)"],
        f"Quota Threshold at 80% — {TENANT}",
        ["Quota Threshold has reached", "80%", TENANT, WHEN, "Current value: 81% (ASR)"],
    ),
    (
        "BUDGET_THRESHOLD", ["80", WHEN, "81%"],
        f"Budget Threshold at 80% — {TENANT}",
        ["Budget Threshold has reached", "80%", TENANT, WHEN, "Current value: 81%"],
    ),
    (
        "ERROR_RATE_4XX", ["5", WHEN, "6.2"], "4xx Error Rate — Threshold 5%",
        ["4xx Error Rate has reached the configured threshold of", "5%", WHEN, "Current Value: 6.2%"],
    ),
    (
        "ERROR_RATE_5XX", ["5", WHEN, "6.2"], "5xx Error Rate — Threshold 5%",
        ["5xx Error Rate has reached the configured threshold of", "5%", WHEN, "Current Value: 6.2%"],
    ),
    (
        "LATENCY_P50", ["1", WHEN, "1.4"], "P50 Latency — Threshold 1s",
        ["P50 Latency has reached the configured threshold of", "1s", WHEN, "Current Value: 1.4s"],
    ),
    (
        "LATENCY_P95", ["2", WHEN, "2.5"], "P95 Latency — Threshold 2s",
        ["P95 Latency has reached the configured threshold of", "2s", WHEN, "Current Value: 2.5s"],
    ),
    (
        "LATENCY_P99", ["3", WHEN, "3.5"], "P99 Latency — Threshold 3s",
        ["P99 Latency has reached the configured threshold of", "3s", WHEN, "Current Value: 3.5s"],
    ),
]


@pytest.mark.parametrize("event_name,details,subject,expected", CASES, ids=[c[0] for c in CASES])
def test_render_maps_details_onto_the_event_template(event_name, details, subject, expected):
    message = _render(event_name, details)

    assert message.to == "a@b.com"
    assert message.subject == subject
    for substring in ["Dear Priya,", *expected]:
        assert substring in message.html_body, f"{substring!r} missing from html_body"
        assert substring in message.text_body, f"{substring!r} missing from text_body"


def test_every_catalog_event_has_a_template():
    assert {c[0] for c in CASES} == {name.value for name in NotificationName}


@pytest.mark.parametrize("event_name", ["ERROR_RATE_4XX", "LATENCY_P95"])
def test_monitoring_alerts_carry_no_institution(event_name):
    message = _render(event_name, ["5", WHEN, "6"], tenant_name="PLATFORM")

    assert "PLATFORM" not in message.subject
    assert "PLATFORM" not in message.html_body
    assert "PLATFORM" not in message.text_body


def test_list_detail_renders_as_indented_lines_in_text():
    message = _render("TIER_ASSIGNED", ["Gold", "desc", ["ASR: 1 req/mo", "NMT: 2 req/mo"]])

    assert "Quota Limits:\n ASR: 1 req/mo\n NMT: 2 req/mo\n" in message.text_body


def test_missing_recipient_name_greets_generically():
    message = _render("BUDGET_ASSIGNED", ["INR", "1"], recipient_name=None)

    assert "Dear there," in message.html_body
    assert "Dear there," in message.text_body


def test_values_are_escaped_in_html_only():
    message = _render("BUDGET_ASSIGNED", ["INR", "<b>1</b>"], tenant_name="A & B")

    assert "A &amp; B" in message.html_body
    assert "&lt;b&gt;1&lt;/b&gt;" in message.html_body
    assert "<b>1</b>" in message.text_body
    assert message.subject == "Budget Assigned — A & B"


def test_extra_details_are_ignored():
    message = _render("BUDGET_ASSIGNED", ["INR", "1", "unused"])

    assert "Budget: INR 1" in message.text_body


def test_a_missing_detail_fails_the_render():
    with pytest.raises(UndefinedError):
        _render("BUDGET_UPDATED", ["INR", "1"])


def test_an_unknown_event_name_fails_the_render():
    with pytest.raises(TemplateNotFound):
        _render("NOT_AN_EVENT", [])


def test_portal_link_uses_configured_url(monkeypatch):
    monkeypatch.setattr(get_settings(), "PORTAL_URL", "https://portal.example.com")

    for event_name, details in (("BUDGET_ASSIGNED", ["INR", "1"]), ("LATENCY_P50", ["1", WHEN, "1.4"])):
        message = _render(event_name, details)
        assert 'href="https://portal.example.com"' in message.html_body
        assert "https://portal.example.com" in message.text_body


def test_portal_link_falls_back_to_plain_text_when_unset():
    message = _render("BUDGET_ASSIGNED", ["INR", "1"])

    assert "Log in to the AI4I-Orchestrate Portal to view full details." in message.text_body
    assert "href=" not in message.text_body
