"""Sends the email directly — no auth-service call. Wraps ai4i_core.email
the same way auth-service's own auth_email_templates.py does: one shared
EmailClient + TemplateRenderer, template files under this consumer's own
templates/emails/ (design doc §8's "Templates folder"), one <event_name in
lowercase>.html + .txt pair per notification.

The client/renderer are built once per process (module-level), not per
message — EmailSettings reads the environment once, and TemplateRenderer's
Jinja Environment is reusable across renders.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from ai4i_core.email import EmailClient, EmailMessage, TemplateRenderer
from ai4i_core.email.providers.factory import build_provider
from ai4i_core.email.settings import EmailSettings
from ai4i_core.logging import get_logger

from consumers.notification_consumer.recipients import Recipient

logger = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "emails"

# One subject line per event_name, filled from `details`. Kept separate from
# the .html/.txt template bodies — the subject is plain text (no HTML), and
# every event needs one whether or not its body needs much filling in.
_SUBJECTS: Dict[str, str] = {
    "TIER_ASSIGNED": "Your plan has been set to {tier_name}",
    "TIER_CHANGED": "Your plan changed from {previous} to {current}",
    "BUDGET_ASSIGNED": "A budget of {current} has been set for your account",
    "BUDGET_UPDATED": "Your budget changed from {previous} to {current}",
    "QUOTA_LIMIT_UPDATED": "Your {inference_name} quota changed from {previous} to {current}",
    "QUOTA_EXHAUSTED": "Your {inference_name} quota is fully used",
    "BUDGET_EXHAUSTED": "Your budget is fully used",
    "QUOTA_THRESHOLD": "Your {inference_name} quota has reached {percent}%",
    "BUDGET_THRESHOLD": "Your budget has reached {percent}%",
}


@lru_cache(maxsize=1)
def _client() -> EmailClient:
    settings = EmailSettings()
    return EmailClient(build_provider(settings))


@lru_cache(maxsize=1)
def _renderer() -> TemplateRenderer:
    return TemplateRenderer([_TEMPLATE_DIR])


def _subject_for(event_name: str, details: Dict[str, Any]) -> str:
    template = _SUBJECTS.get(event_name, "Notification: {event_name}")
    try:
        return template.format(event_name=event_name, **details)
    except (KeyError, IndexError):
        logger.warning(
            "Subject template for %s references a missing details key — using a bare fallback",
            event_name,
        )
        return f"Notification: {event_name}"


async def send_one(*, recipient: Recipient, event_name: str, details: Dict[str, Any]) -> bool:
    """True on a confirmed send. Never raises — provider failures are
    logged and reported as False (EmailClient.send_safe), so one bad
    recipient can't take the others down."""
    ctx = {**details, "recipient_name": recipient.display_name}
    html_body, text_body = _renderer().render(event_name.lower(), ctx)
    message = EmailMessage(
        to=recipient.email,
        subject=_subject_for(event_name, details),
        html_body=html_body,
        text_body=text_body,
    )
    return await _client().send_safe(message)
