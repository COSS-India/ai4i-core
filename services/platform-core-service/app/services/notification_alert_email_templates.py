"""Notification / Alert email templates.

Fixed, backend-only templates — not editable from the Portal. Callers (the
notification and alert trigger code) supply already-formatted display
strings; this module only renders and wraps them into an EmailMessage. Send
it with ``app.services.email_helpers.enqueue_email`` (or ``EmailClient.send``
/ ``send_safe`` directly) — this module never sends mail itself.

Every event renders through one of two generic templates:

- ``render_notification_email`` — Standard Notification Email Template.
  Body shape is a fixed "[Notification Headline] / [Notification Details]",
  per the Reference Email Template spec.
- ``render_alert_email`` — Standard Alert Email Template. Body shape is
  fixed: "[Alert Name] has reached [Threshold]% ... Current value:
  [Current Value]".

Every other function here (Tier Assigned, Budget Exhausted, Quota Threshold
Alert, etc.) is a convenience wrapper around one of those two — it just
builds the right headline/details (or alert_name) from typed parameters, so
callers get a named function with the correct wording baked in instead of
having to hand-format that text (or remember a magic string like
``alert_name="Quota Threshold"``) at every call site.

Templates live alongside this module under app/templates/emails/.
"""

from pathlib import Path
from typing import List

from ai4i_core.email import EmailMessage, TemplateRenderer

from app.core.config import settings

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"
_renderer = TemplateRenderer([_TEMPLATE_DIR])


def _render(template: str, *, to: str, subject: str, ctx: dict) -> EmailMessage:
    html, text = _renderer.render(template, {**ctx, "portal_url": settings.portal_url})
    return EmailMessage(to=to, subject=subject, html_body=html, text_body=text)


def render_notification_email(
    *,
    to: str,
    recipient_name: str,
    notification_name: str,
    institution_name: str,
    notification_headline: str,
    notification_details: List[str],
) -> EmailMessage:
    """Standard Notification Email Template.

    ``notification_headline`` is one pre-formatted sentence (e.g. "A Tier has
    been assigned to Acme Bank."). ``notification_details`` is a list of
    pre-formatted lines (e.g. ["Tier: Gold", "Rate Limit: 1000", ...]) — a
    list rather than one string because several notification types repeat a
    line per Model Task Type. The caller owns all formatting; this function
    only fills the fixed template shape.
    """
    return _render(
        "notification",
        to=to,
        subject=f"{notification_name} — {institution_name}",
        ctx={
            "recipient_name": recipient_name,
            "notification_name": notification_name,
            "institution_name": institution_name,
            "notification_headline": notification_headline,
            "notification_details": notification_details,
        },
    )


def render_alert_email(
    *,
    to: str,
    recipient_name: str,
    alert_name: str,
    institution_name: str,
    alert_datetime: str,
    threshold: str,
    current_value: str,
) -> EmailMessage:
    """Standard Alert Email Template.

    ``threshold`` and ``current_value`` are pre-formatted display strings
    (e.g. "80", "92.4") — the caller owns numeric formatting. ``alert_datetime``
    is the pre-formatted date/time the alert fired.
    """
    return _render(
        "alert",
        to=to,
        subject=f"{alert_name} at {threshold}% — {institution_name}",
        ctx={
            "recipient_name": recipient_name,
            "alert_name": alert_name,
            "institution_name": institution_name,
            "alert_datetime": alert_datetime,
            "threshold": threshold,
            "current_value": current_value,
        },
    )


# ── Configuration Update Notifications — convenience wrappers around
# render_notification_email (see module docstring) ──


def render_tier_assigned_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    tier_name: str,
    tier_description: str,
    quota_lines: List[str],
    rate_limit_value: str,
    effective_from: str,
    effective_to: str,
) -> EmailMessage:
    """``quota_lines`` are pre-formatted "Task Type: Quota Limit" strings, one per line."""
    details = [
        f"Tier: {tier_name}",
        f"Description: {tier_description}",
        "Quota Limits:",
        *[f" {line}" for line in quota_lines],
        f"Rate Limit: {rate_limit_value}",
        f"Effective From: {effective_from}",
        f"Effective To: {effective_to}",
    ]
    return render_notification_email(
        to=to,
        recipient_name=recipient_name,
        notification_name="Tier Assigned",
        institution_name=institution_name,
        notification_headline=f"A Tier has been assigned to {institution_name}.",
        notification_details=details,
    )


def render_budget_assigned_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    currency: str,
    budget_amount: str,
) -> EmailMessage:
    return render_notification_email(
        to=to,
        recipient_name=recipient_name,
        notification_name="Budget Assigned",
        institution_name=institution_name,
        notification_headline=f"A Budget has been assigned to {institution_name}.",
        notification_details=[f"Budget: {currency} {budget_amount}"],
    )


def render_tier_reassigned_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    current_tier_name: str,
    new_tier_name: str,
    new_tier_description: str,
    quota_lines: List[str],
    new_rate_limit_value: str,
    effective_from: str,
    effective_to: str,
) -> EmailMessage:
    """``quota_lines`` are the NEW Tier's pre-formatted "Task Type: Quota Limit" strings."""
    details = [
        f"Current Tier: {current_tier_name} → New Tier: {new_tier_name}",
        f"New Tier Description: {new_tier_description}",
        "New Tier Quota Limits:",
        *[f" {line}" for line in quota_lines],
        f"New Tier Rate Limit: {new_rate_limit_value}",
        f"Effective From: {effective_from}",
        f"Effective To: {effective_to}",
    ]
    return render_notification_email(
        to=to,
        recipient_name=recipient_name,
        notification_name="Tier Reassignment",
        institution_name=institution_name,
        notification_headline=f"The Tier for {institution_name} has been reassigned.",
        notification_details=details,
    )


def render_quota_limit_updated_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    tier_name: str,
    changes: List[str],
    effective_date: str,
) -> EmailMessage:
    """``changes`` are pre-formatted "Task Type: changed from X to Y" strings,
    one per Model Task Type updated."""
    details = [f"Tier: {tier_name}", *changes, f"Effective Date: {effective_date}"]
    return render_notification_email(
        to=to,
        recipient_name=recipient_name,
        notification_name="Quota Limit Updated",
        institution_name=institution_name,
        notification_headline=f"The Quota Limit for {institution_name} has been updated.",
        notification_details=details,
    )


def render_budget_revised_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    currency: str,
    previous_value: str,
    new_value: str,
    effective_date: str,
) -> EmailMessage:
    return render_notification_email(
        to=to,
        recipient_name=recipient_name,
        notification_name="Budget Revised",
        institution_name=institution_name,
        notification_headline=f"The Budget for {institution_name} has been revised.",
        notification_details=[
            f"Budget changed from {currency} {previous_value} to {currency} {new_value}",
            f"Effective Date: {effective_date}",
        ],
    )


def render_quota_exhausted_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    tier_name: str,
    exhausted_lines: List[str],
) -> EmailMessage:
    """``exhausted_lines`` are pre-formatted "Task Type: Quota Limit X, Resets on Y"
    strings, one per Model Task Type exhausted."""
    details = [f"Tier: {tier_name}", *exhausted_lines]
    return render_notification_email(
        to=to,
        recipient_name=recipient_name,
        notification_name="Quota Exhausted",
        institution_name=institution_name,
        notification_headline=f"The Quota for {institution_name} has been fully consumed.",
        notification_details=details,
    )


def render_budget_exhausted_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    currency: str,
    budget_amount: str,
) -> EmailMessage:
    return render_notification_email(
        to=to,
        recipient_name=recipient_name,
        notification_name="Budget Exhausted",
        institution_name=institution_name,
        notification_headline=f"The Budget for {institution_name} has been fully consumed.",
        notification_details=[f"Budget: {currency} {budget_amount}"],
    )


# ── PPU-15: Proactive Governance Notifications ──


def render_quota_threshold_alert_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    threshold: str,
    alert_datetime: str,
    current_value: str,
) -> EmailMessage:
    """Tenant-admin-facing quota threshold alert. ``current_value`` is the
    actual % of Quota consumed at the time of the alert."""
    return render_alert_email(
        to=to,
        recipient_name=recipient_name,
        alert_name="Quota Threshold",
        institution_name=institution_name,
        alert_datetime=alert_datetime,
        threshold=threshold,
        current_value=current_value,
    )


def render_budget_threshold_alert_email(
    *,
    to: str,
    recipient_name: str,
    institution_name: str,
    threshold: str,
    alert_datetime: str,
    current_value: str,
) -> EmailMessage:
    """Tenant-admin-facing budget threshold alert. ``current_value`` is the
    actual % of Budget consumed at the time of the alert."""
    return render_alert_email(
        to=to,
        recipient_name=recipient_name,
        alert_name="Budget Threshold",
        institution_name=institution_name,
        alert_datetime=alert_datetime,
        threshold=threshold,
        current_value=current_value,
    )


