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
# MUST stay >= EmailSettings.smtp_timeout — a deadline shorter than
# smtp_timeout cuts off sends aiosmtplib would still have completed (seen
# in practice with SES sends taking ~21-25s). Headroom is 0 by design:
# SMTP_TIMEOUT is 60s in env.template and this deadline matches it. If
# DNS/connect-phase hangs show up in practice, bump this above 0 rather than
# shortening SMTP_TIMEOUT.
_DEADLINE_HEADROOM_S = 0.0


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
