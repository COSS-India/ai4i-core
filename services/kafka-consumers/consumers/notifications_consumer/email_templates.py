"""Renders the email for any event_name — one function, no per-event code.

Each event has one template definition, templates/emails/events/<event_name>.j2,
which holds its wording and names the envelope's ``details`` positionally
(``details[0]`` is the first value, and so on). It also names the layout it
renders through: notification, alert or monitoring_alert. email.html,
email.txt and email.subject.txt pick that file up by event_name, so adding
an event is a new .j2 file, not code.

Nothing here reads, counts or checks ``details``. A value the template
needs and the producer did not send fails the render (StrictUndefined); the
caller treats that as a failed send.
"""

from pathlib import Path
from typing import Any, List, Optional

from ai4i_core.email import EmailMessage, TemplateRenderer

from consumers.notifications_consumer.config import get_settings

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "emails"
_renderer = TemplateRenderer([_TEMPLATE_DIR])


def render_email(
    *, to: str, recipient_name: Optional[str], event_name: str, tenant_name: Optional[str], details: List[Any],
) -> EmailMessage:
    ctx = {
        "event_name": event_name,
        "tenant_name": tenant_name,
        "recipient_name": recipient_name,
        "details": details,
        "portal_url": get_settings().PORTAL_URL,
    }
    html, text = _renderer.render("email", ctx)
    subject = _renderer.render_text("email.subject", ctx)
    return EmailMessage(to=to, subject=subject, html_body=html, text_body=text)
