"""Sends one email — no auth-service call, no per-event knowledge.

The client is built once per process (module-level), not per message —
EmailSettings reads the environment once. email_templates.render_email
builds the message; this module only reports whether the send succeeded
within its deadline.
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
    return EmailClient(build_provider(settings))


@lru_cache(maxsize=1)
def _send_deadline_s() -> float:
    return EmailSettings().smtp_timeout + _DEADLINE_HEADROOM_S


async def send(
    *, recipient: Any, event_name: str, tenant_name: Optional[str], details: List[Any],
) -> bool:
    """True on a confirmed send to one envelope recipient ({"email", "name"}).
    Never raises and never blocks past _send_deadline_s(): a render error, a
    provider failure or a hang is logged and reported as False, so one bad
    recipient can't take the others (or the consumer) down with it."""
    deadline = _send_deadline_s()
    try:
        message = email_templates.render_email(
            to=recipient["email"], recipient_name=recipient.get("name"),
            event_name=event_name, tenant_name=tenant_name, details=details,
        )
        return await asyncio.wait_for(_client().send_safe(message), timeout=deadline)
    except asyncio.TimeoutError:
        logger.error(
            "Email send timed out after %.0fs — treating as failed | to=%s event_name=%s",
            deadline, recipient.get("email"), event_name,
        )
        return False
    except Exception:
        logger.exception("Email send failed | recipient=%r event_name=%s", recipient, event_name)
        return False
