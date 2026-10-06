"""Sends one email — no auth-service call, no per-event knowledge.

The client is built once per process (module-level), not per message —
EmailSettings reads the environment once. email_templates.render_email
builds the message; this module only reports whether the send succeeded
within its deadline, and if not, the exception that stopped it.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, List, Optional

from ai4i_core.email import EmailClient
from ai4i_core.email.providers.factory import build_provider
from ai4i_core.email.settings import EmailSettings
from ai4i_core.logging import get_logger

from consumers.notifications_consumer import email_templates
from consumers.notifications_consumer.config import get_settings

logger = get_logger(__name__)

# Belt-and-braces on top of EmailSettings.smtp_timeout (which aiosmtplib.send
# is given directly): a hung DNS lookup or a silently-dropped TCP connect
# (a firewall dropping outbound SMTP with no RST, common on WSL/corporate
# networks) isn't guaranteed to be covered by the provider's own timeout, and
# this consumer's loop is fully sequential — one stuck send blocks every
# other Kafka message behind it, and eventually costs the group its
# partition (KAFKA_MAX_POLL_INTERVAL_MS). A hard deadline here means a
# send that can't complete becomes "failed", not "wedged forever".
#
# MUST stay strictly ABOVE 0 — headroom at 0 means this outer wait_for and
# aiosmtplib's own internal timeout (smtp.py's `timeout=self._timeout`,
# the same smtp_timeout value) expire at the same instant, so this cancels
# the send in a race against aiosmtplib's own completion rather than after
# it. Confirmed in staging (2026-09-30): a real SES send that had already
# been accepted by the far end was still cancelled by this wait_for at the
# same moment, logged "timed out — treating as failed", and recorded as a
# failed delivery — even though the recipient received the email. 15s of
# headroom gives aiosmtplib's own timeout (or a real success) a chance to
# resolve first; only a send stuck well past smtp_timeout — a true hang,
# not just a slow-but-completing one — still hits this outer deadline.
# KAFKA_MAX_POLL_INTERVAL_MS (300s in env.template) has ample room for the
# extra wait on a single message.
_DEADLINE_HEADROOM_S = 15.0


@lru_cache(maxsize=1)
def _client() -> EmailClient:
    settings = EmailSettings()
    settings = settings.model_copy(
        update={
            "email_from_name": get_settings().resolve_smtp_from_name(settings.email_from_name)
        }
    )
    return EmailClient(build_provider(settings))


@lru_cache(maxsize=1)
def _send_deadline_s() -> float:
    return EmailSettings().smtp_timeout + _DEADLINE_HEADROOM_S


async def send(
    *, recipient: Any, event_name: str, tenant_name: Optional[str], details: List[Any],
) -> Optional[BaseException]:
    """Send to one envelope recipient ({"email", "name"}): None on a confirmed
    send, else the exception that stopped it — a render error (e.g. jinja2's
    UndefinedError for a detail the producer didn't send), the provider's
    EmailDeliveryError, or TimeoutError past _send_deadline_s(). Never raises,
    so one bad recipient can't take the others (or the consumer) down with it."""
    deadline = _send_deadline_s()
    try:
        message = email_templates.render_email(
            to=recipient["email"], recipient_name=recipient.get("name"),
            event_name=event_name, tenant_name=tenant_name, details=details,
        )
        await asyncio.wait_for(_client().send(message), timeout=deadline)
        return None
    except asyncio.TimeoutError as exc:
        logger.error(
            "Email send timed out after %.0fs — treating as failed | to=%s event_name=%s",
            deadline, recipient.get("email"), event_name,
        )
        return exc
    except Exception as exc:
        logger.exception("Email send failed | recipient=%r event_name=%s", recipient, event_name)
        return exc
