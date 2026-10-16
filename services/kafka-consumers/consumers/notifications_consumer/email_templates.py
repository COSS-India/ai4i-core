"""Renders the email for any event_name — one function, no per-event code.

Each event has one template definition, templates/emails/events/<event_name>.j2,
which holds its wording and names the envelope's ``details`` positionally
(``details[0]`` is the first value, and so on). It also names the layout it
renders through: notification, alert or monitoring_alert. email.html,
email.txt and email.subject.txt pick that file up by event_name, so adding
an event is a new .j2 file, not code.

Nothing here counts or checks ``details``. A value the template needs and
the producer did not send fails the render (StrictUndefined); the caller
treats that as a failed send. A value the producer sent empty (None, a
blank string or an empty list) renders as "NA" instead of a blank field.
"""

from pathlib import Path
from typing import Any, List, Optional

from ai4i_core.email import EmailMessage, TemplateRenderer

from consumers.notifications_consumer.config import get_settings

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "emails"
_renderer = TemplateRenderer([_TEMPLATE_DIR])

# Shown wherever the producer sent no value, rather than a blank field.
NO_VALUE = "NA"


def _or_na(value: Any) -> Any:
    """``value`` with every empty field replaced by NO_VALUE, through nested
    lists. A list stays a list (an empty one becomes [NO_VALUE]) so a
    template that iterates it still can. Numbers, including 0, are kept."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return NO_VALUE
    if isinstance(value, (list, tuple)):
        return [_or_na(v) for v in value] or [NO_VALUE]
    return value


def render_email(
    *, to: str, recipient_name: Optional[str], event_name: str, tenant_name: Optional[str], details: List[Any],
) -> EmailMessage:
    settings = get_settings()
    ctx = {
        "event_name": event_name,
        "tenant_name": _or_na(tenant_name),
        "recipient_name": recipient_name,
        "details": [_or_na(d) for d in details],
        "portal_url": settings.PORTAL_URL,
        "platform_name": settings.get_platform_name(),
        "logo_url": settings.get_adopter_logo_url(),
    }
    html, text = _renderer.render("email", ctx)
    subject = _renderer.render_text("email.subject", ctx)
    return EmailMessage(to=to, subject=subject, html_body=html, text_body=text)
