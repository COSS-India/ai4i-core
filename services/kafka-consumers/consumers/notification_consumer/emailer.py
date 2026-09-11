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

import asyncio
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

# Belt-and-braces on top of EmailSettings.smtp_timeout (which aiosmtplib.send
# is given directly): a hung DNS lookup or a silently-dropped TCP connect
# (a firewall dropping outbound SMTP with no RST, common on WSL/corporate
# networks) isn't guaranteed to be covered by the provider's own timeout, and
# this consumer's loop is fully sequential — one stuck send blocks every
# other Kafka message behind it, and eventually costs the group its
# partition (KAFKA_MAX_POLL_INTERVAL_MS). A hard deadline here means a
# send that can't complete becomes "failed", not "wedged forever".
_SEND_DEADLINE_S = 20.0

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
    """True on a confirmed send. Never raises and never blocks past
    _SEND_DEADLINE_S — provider failures are logged and reported as False
    (EmailClient.send_safe), and a hang past the deadline is treated the
    same way, so one bad or unreachable recipient can't take the others
    (or the whole consumer) down with it."""
    try:
        ctx = {**details, "recipient_name": recipient.display_name}
        html_body, text_body = _renderer().render(event_name.lower(), ctx)
        message = EmailMessage(
            to=recipient.email,
            subject=_subject_for(event_name, details),
            html_body=html_body,
            text_body=text_body,
        )
        return await asyncio.wait_for(_client().send_safe(message), timeout=_SEND_DEADLINE_S)
    except asyncio.TimeoutError:
        logger.error(
            "Email send timed out after %.0fs — treating as failed | to=%s event_name=%s",
            _SEND_DEADLINE_S, recipient.email, event_name,
        )
        return False
    except Exception:
        # Render lives inside this try too (a StrictUndefined miss on a
        # details key this event_name's template expects, or a malformed
        # template) — this function's contract is "never raises", so any
        # failure here is reported as False, not propagated. delivery.py's
        # gather(return_exceptions=True) is a second, independent guard
        # against this same class of bug, not a substitute for it.
        logger.exception(
            "send_one failed before/during send | to=%s event_name=%s",
            recipient.email, event_name,
        )
        return False
