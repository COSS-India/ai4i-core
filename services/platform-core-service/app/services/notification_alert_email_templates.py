"""Standard Notification / Alert email templates.

Fixed, backend-only templates per the Reference Email Template spec — not
editable from the Portal. Callers (the notification and alert trigger code)
supply already-formatted display strings; this module only renders and wraps
them into an EmailMessage. Send it with ``app.services.email_helpers.
enqueue_email`` (or ``EmailClient.send`` / ``send_safe`` directly) — this
module never sends mail itself.

Templates live alongside this module under app/templates/emails/.
"""

from pathlib import Path

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
    effective_date: str,
    notification_details: str,
) -> EmailMessage:
    """Standard Notification Email Template.

    All fields are pre-formatted display strings — the caller (notification
    trigger code) owns formatting (e.g. dates, amounts, "Tier changed from X
    to Y" phrasing); this function only fills the fixed template shape.
    """
    return _render(
        "notification",
        to=to,
        subject=f"{notification_name} — {institution_name}",
        ctx={
            "recipient_name": recipient_name,
            "notification_name": notification_name,
            "institution_name": institution_name,
            "effective_date": effective_date,
            "notification_details": notification_details,
        },
    )


def render_alert_email(
    *,
    to: str,
    recipient_name: str,
    alert_name: str,
    institution_name: str,
    effective_date: str,
    threshold: str,
    current_value: str,
) -> EmailMessage:
    """Standard Alert Email Template.

    ``threshold`` and ``current_value`` are pre-formatted display strings
    (e.g. "80", "92.4") — the caller owns numeric formatting.
    """
    return _render(
        "alert",
        to=to,
        subject=f"{alert_name} at {threshold}% — {institution_name}",
        ctx={
            "recipient_name": recipient_name,
            "alert_name": alert_name,
            "institution_name": institution_name,
            "effective_date": effective_date,
            "threshold": threshold,
            "current_value": current_value,
        },
    )
