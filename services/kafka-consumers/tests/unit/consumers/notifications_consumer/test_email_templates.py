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
from pydantic import ValidationError

from consumers.notifications_consumer import email_templates as templates
from consumers.notifications_consumer.config import Settings, get_settings

# Supplied by tests/conftest.py as PLATFORM_NAME — the code itself has no default.
BRAND = "Test Platform"

TENANT = "IIT Madras"
WHEN = "28 Sep 2026, 03:45 PM IST"


@pytest.fixture(autouse=True)
def _no_portal_url(monkeypatch):
    """Default to no PORTAL_URL so the plain-text fallback wording is asserted
    consistently; the portal-link tests override this."""
    monkeypatch.setattr(get_settings(), "PORTAL_URL", None)


@pytest.fixture(autouse=True)
def _default_branding(monkeypatch):
    """Pin the brand so a local .env's PLATFORM_NAME / ADOPTER_LOGO_URL can't
    change what these tests assert; the branding tests below override it."""
    monkeypatch.setattr(get_settings(), "PLATFORM_NAME", BRAND)
    monkeypatch.setattr(get_settings(), "ADOPTER_LOGO_URL", None)


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
        # The Adopter Admin's one consolidated copy across several
        # institutions (emit_state_bulk) carries a 4th details element:
        # the list of affected institution names.
        "QUOTA_LIMIT_UPDATED",
        ["Gold", ["ASR: changed from 10,000 to 15,000"], "2026-10-01", ["Force India", "Mahindra India"]],
        f"Quota Limit Updated — {TENANT}",
        ["Tier: Gold", "ASR: changed from 10,000 to 15,000", "Effective Date: 2026-10-01",
         "Institutions:", "Force India", "Mahindra India"],
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


# 12:27 — asr, llm and tts all cross 5xx in one tick: the evaluator's one event.
GROUPED = ["5", WHEN, "11.3", "tts-service", [
    ["tts-service", "11.3", "10"], ["asr-service", "9.1", "5"], ["llm-service", "6.2", "5"],
]]


def test_services_over_one_alert_in_one_tick_are_listed_in_one_email():
    message = _render("ERROR_RATE_5XX", GROUPED, tenant_name=None)

    assert message.subject == "5xx Error Rate — Threshold 5%"
    assert (
        "Affected Services:\n"
        " tts-service — Current Value: 11.3% (Threshold 10%)\n"
        " asr-service — Current Value: 9.1%\n"
        " llm-service — Current Value: 6.2%\n"
        "\nLog in to"
    ) in message.text_body
    html = message.html_body
    assert "Affected Services:" in html
    assert (
        html.index("tts-service — Current Value: 11.3% (Threshold 10%)")
        < html.index("asr-service — Current Value: 9.1%")
        < html.index("llm-service — Current Value: 6.2%")
        < html.index("Log in to")
    )
    # The list replaces the single-service lines.
    for body in (message.text_body, html):
        assert "Affected Service:" not in body
        assert "\nCurrent Value:" not in body and ">Current Value:" not in body


def test_a_service_that_fired_alone_keeps_the_single_service_lines():
    message = _render("ERROR_RATE_5XX", ["5", WHEN, "6.2", "asr-service"], tenant_name=None)

    assert "Current Value: 6.2%\nAffected Service: asr-service\n\nLog in to" in message.text_body
    assert "Affected Services" not in message.text_body + message.html_body
    html = message.html_body
    assert '<p style="margin:0 0 4px 0;">Current Value: 6.2%</p>' in html
    assert '<p style="margin:0 0 20px 0;">Affected Service: asr-service</p>' in html


@pytest.mark.parametrize("event_name", ["ERROR_RATE_4XX", "ERROR_RATE_5XX", "LATENCY_P50", "LATENCY_P95", "LATENCY_P99"])
def test_every_monitoring_alert_shows_the_affected_service(event_name):
    message = _render(event_name, ["5", WHEN, "6", "svc-a"], tenant_name=None)

    assert "Affected Service: svc-a" in message.html_body
    assert "Affected Service: svc-a" in message.text_body


def test_monitoring_envelope_without_a_service_still_renders():
    """An envelope published before the producer sent the service (still in
    Kafka, or retried, during a rollout) renders without the line."""
    message = _render("LATENCY_P95", ["2", WHEN, "2.5"], tenant_name=None)

    assert "Current Value: 2.5s\n\nLog in to" in message.text_body
    assert "Affected Service" not in message.text_body
    assert "Affected Service" not in message.html_body
    assert '<p style="margin:0 0 20px 0;">Current Value: 2.5s</p>' in message.html_body


def test_affected_service_is_escaped_in_html_only():
    message = _render("ERROR_RATE_4XX", ["5", WHEN, "6", "<b>svc</b>"], tenant_name=None)

    assert "Affected Service: &lt;b&gt;svc&lt;/b&gt;" in message.html_body
    assert "Affected Service: <b>svc</b>" in message.text_body


def test_listed_services_are_escaped_in_html_only():
    details = ["5", WHEN, "9", "<b>a</b>", [["<b>a</b>", "9", "5"], ["b", "6", "5"]]]
    message = _render("ERROR_RATE_4XX", details, tenant_name=None)

    assert "&lt;b&gt;a&lt;/b&gt; — Current Value: 9%" in message.html_body
    assert " <b>a</b> — Current Value: 9%" in message.text_body


@pytest.mark.parametrize("event_name", ["ERROR_RATE_4XX", "ERROR_RATE_5XX", "LATENCY_P50", "LATENCY_P95", "LATENCY_P99"])
def test_every_monitoring_alert_lists_grouped_services(event_name):
    details = ["1", WHEN, "3", "svc-b", [["svc-b", "3", "1"], ["svc-a", "2", "1"]]]
    message = _render(event_name, details, tenant_name=None)

    for body in (message.html_body, message.text_body):
        assert "Affected Services:" in body
        assert "svc-b — Current Value: 3" in body and "svc-a — Current Value: 2" in body


def test_a_one_service_list_renders_the_single_service_lines():
    """The producer sends a lone service without the list, but a one-entry
    list must not render a one-line 'Affected Services' block."""
    message = _render("ERROR_RATE_5XX", ["5", WHEN, "6.2", "asr-service", [["asr-service", "6.2", "5"]]], tenant_name=None)

    assert "Current Value: 6.2%\nAffected Service: asr-service\n" in message.text_body
    assert "Affected Services" not in message.text_body


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

    assert f"Log in to the {BRAND} Portal to view full details." in message.text_body
    assert "href=" not in message.text_body


# ── Branding (PLATFORM_NAME / ADOPTER_LOGO_URL — same pair as auth-service) ──

# One event per layout: notification, alert, monitoring_alert.
_BRANDING_RENDERERS = [
    lambda: _render("BUDGET_ASSIGNED", ["INR", "500000"]),
    lambda: _render("QUOTA_THRESHOLD", ["80", "2026-09-10", "81%"]),
    lambda: _render("LATENCY_P95", ["5", "2026-09-28", "7.3"]),
]


@pytest.mark.parametrize("render", _BRANDING_RENDERERS, ids=["notification", "alert", "monitoring_alert"])
def test_platform_name_comes_from_settings(monkeypatch, render):
    monkeypatch.setattr(get_settings(), "PLATFORM_NAME", "Custom Brand")

    message = render()

    for body in (message.html_body, message.text_body):
        assert "Log in to the Custom Brand Portal to view full details." in body
        assert "Custom Brand Team" in body
        assert BRAND not in body
        assert "AI Switch" not in body
    assert "&copy; Custom Brand" in message.html_body


class TestPlatformNameRequired:
    """No in-code default: a missing/blank PLATFORM_NAME must stop the consumer at
    startup, not let it send emails under a baked-in name."""

    def test_missing_platform_name_fails(self, monkeypatch):
        monkeypatch.delenv("PLATFORM_NAME", raising=False)
        with pytest.raises(ValidationError, match="PLATFORM_NAME"):
            Settings(_env_file=None)

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_platform_name_fails(self, monkeypatch, blank):
        # setup-env.sh writes PLATFORM_NAME= (empty) when the root .env leaves it blank.
        monkeypatch.setenv("PLATFORM_NAME", blank)
        with pytest.raises(ValidationError, match="PLATFORM_NAME must be set"):
            Settings(_env_file=None)

    def test_env_value_is_used_and_stripped(self, monkeypatch):
        monkeypatch.setenv("PLATFORM_NAME", "  MahaVistaar  ")
        assert Settings(_env_file=None).get_platform_name() == "MahaVistaar"

    def test_consumer_startup_loads_settings_first(self):
        """Fail-fast relies on main.run() calling get_settings() before any
        Kafka/DB work — pin that so a refactor can't move it to send time,
        where send_one() would swallow the error as a failed email."""
        import inspect

        from consumers.notifications_consumer import main

        source = inspect.getsource(main.run)
        assert source.index("cfg.get_settings()") < source.index("async with infra(")


def test_logo_url_replaces_text_brand_mark_in_header(monkeypatch):
    monkeypatch.setattr(get_settings(), "ADOPTER_LOGO_URL", "https://cdn.example.com/logo.png")

    message = _BRANDING_RENDERERS[2]()

    assert f'<img src="https://cdn.example.com/logo.png" alt="{BRAND}"' in message.html_body


def test_relative_logo_url_is_ignored(monkeypatch):
    monkeypatch.setattr(get_settings(), "ADOPTER_LOGO_URL", "/logo.png")

    message = _BRANDING_RENDERERS[2]()

    assert "<img" not in message.html_body


class TestResolveSmtpFromName:
    """EMAIL_FROM_NAME stays independent of PLATFORM_NAME; it only inherits it when blank."""

    def test_keeps_explicit_from_name(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "PLATFORM_NAME", BRAND)
        assert get_settings().resolve_smtp_from_name("COSS Support") == "COSS Support"

    def test_inherits_platform_name_when_blank(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "PLATFORM_NAME", "Custom Brand")
        assert get_settings().resolve_smtp_from_name("") == "Custom Brand"
        assert get_settings().resolve_smtp_from_name("   ") == "Custom Brand"
