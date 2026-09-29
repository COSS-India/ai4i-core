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
from pydantic import ValidationError

from consumers.notifications_consumer.config import Settings, get_settings

# Supplied by tests/conftest.py as PLATFORM_NAME — the code itself has no default.
BRAND = "Test Platform"


@pytest.fixture(autouse=True)
def _no_portal_url(monkeypatch):
    """Default to no PORTAL_URL so the plain-text fallback wording is asserted
    consistently; test_portal_link_uses_configured_url overrides this."""
    monkeypatch.setattr(get_settings(), "PORTAL_URL", None)


@pytest.fixture(autouse=True)
def _default_branding(monkeypatch):
    """Pin the brand so a local .env's PLATFORM_NAME / ADOPTER_LOGO_URL can't
    change what these tests assert; the branding tests below override it."""
    monkeypatch.setattr(get_settings(), "PLATFORM_NAME", BRAND)
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

    assert f"Log in to the {BRAND} Portal to view full details." in message.text_body
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
        assert BRAND not in body
        assert "AI Switch" not in body
    if render is not _BRANDING_RENDERERS[2]:  # monitoring has no © footer (template spec)
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

    message = _BRANDING_RENDERERS[0]()

    assert f'<img src="https://cdn.example.com/logo.png" alt="{BRAND}"' in message.html_body


def test_relative_logo_url_is_ignored(monkeypatch):
    monkeypatch.setattr(get_settings(), "ADOPTER_LOGO_URL", "/logo.png")

    message = _BRANDING_RENDERERS[0]()

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


class TestMonitoringAffectedService:
    """Standard Monitoring Alert Email Template: "Affected Service: [...]" sits
    directly under "Current Value: [...]", and only "if applicable"."""

    def _render(self, affected_service=None):
        kwargs = dict(
            to="a@b.com", recipient_name="Priya", alert=templates.MonitoringAlertName.ERROR_RATE_5XX,
            threshold="5", alert_datetime="2026-09-28 10:00 IST", current_value="6.2",
        )
        if affected_service is not None:
            kwargs["affected_service"] = affected_service
        return templates.render_monitoring_alert_email(**kwargs)

    def test_text_body_matches_the_template_line_for_line(self):
        lines = [l for l in self._render("Legal Translate v2").text_body.splitlines() if l.strip()]
        start = lines.index("Dear Priya,")
        assert lines[start:start + 6] == [
            "Dear Priya,",
            "5xx Error Rate has reached the configured threshold of 5% as of 2026-09-28 10:00 IST.",
            "Current Value: 6.2%",
            "Affected Service: Legal Translate v2",
            f"Log in to the {BRAND} Portal to view full details.",
            "Regards,",
        ]

    def test_html_body_has_the_line(self):
        assert "Affected Service: Legal Translate v2" in self._render("Legal Translate v2").html_body

    def test_line_is_omitted_when_not_applicable(self):
        # Existing callers that don't pass it at all behave exactly as before.
        for message in (self._render(), self._render("")):
            assert "Affected Service" not in message.text_body
            assert "Affected Service" not in message.html_body

    def test_service_name_is_html_escaped(self):
        message = self._render("<b>x</b> & y")
        assert "Affected Service: &lt;b&gt;x&lt;/b&gt; &amp; y" in message.html_body


def _visible_html_lines(html_body: str) -> list:
    """Text a reader actually sees in the HTML email, one entry per line."""
    import html as _html
    import re

    body = re.sub(r"(?s)<head>.*?</head>", "", html_body)
    body = " ".join(body.split())  # source line breaks render as spaces
    body = re.sub(r"<br\s*/?>|</p>", "\n", body)
    body = _html.unescape(re.sub(r"<[^>]+>", " ", body))
    return [" ".join(line.split()) for line in body.splitlines() if line.strip()]


class TestMonitoringMatchesTemplateExactly:
    """Only what the Standard Monitoring Alert Email Template lists — no inbox
    preheader, brand header, in-body heading, © footer, or text banner."""

    def _render(self):
        return templates.render_monitoring_alert_email(
            to="a@b.com", recipient_name="Priya", alert=templates.MonitoringAlertName.LATENCY_P95,
            threshold="5", alert_datetime="2026-09-28 10:00 IST", current_value="7.3",
            affected_service="Legal Translate v2",
        )

    EXPECTED = [
        "Dear Priya,",
        "P95 Latency has reached the configured threshold of 5s as of 2026-09-28 10:00 IST.",
        "Current Value: 7.3s",
        "Affected Service: Legal Translate v2",
        f"Log in to the {BRAND} Portal to view full details.",
        "Regards,",
        f"{BRAND} Team",
    ]

    def test_subject(self):
        assert self._render().subject == "P95 Latency — Threshold 5s"

    def test_html_shows_only_the_template_lines(self):
        message = self._render()
        assert _visible_html_lines(message.html_body) == self.EXPECTED
        assert "<h1" not in message.html_body
        assert "&copy;" not in message.html_body

    def test_text_shows_only_the_template_lines(self):
        lines = [line for line in self._render().text_body.splitlines() if line.strip()]
        assert lines == self.EXPECTED


def test_other_emails_keep_header_heading_and_footer():
    """The new _base.html header/footer blocks are opt-out for monitoring only."""
    notification = templates.render_budget_assigned_email(
        to="a@b.com", recipient_name="Priya", institution_name="Acme Bank", currency="INR", budget_amount="500000",
    )
    alert = templates.render_quota_threshold_alert_email(
        to="a@b.com", recipient_name="Priya", institution_name="Acme Bank",
        threshold="80", alert_datetime="2026-09-10", current_value="81",
    )
    for message in (notification, alert):
        assert "<h1" in message.html_body
        assert f"&copy; {BRAND}" in message.html_body
        assert message.text_body.startswith(f"{BRAND}\n====")
