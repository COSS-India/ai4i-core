"""Sends the email directly — no auth-service call, no per-event knowledge.

The client is built once per process (module-level), not per message —
EmailSettings reads the environment once.

email_templates.render_email is the one place that turns (event_name,
tenant_name, details) into an actual message — this module only decides
whether that send succeeded within its deadline, nothing about what's in
it.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, List

from ai4i_core.email import EmailClient
from ai4i_core.email.providers.factory import build_provider
from ai4i_core.email.settings import EmailSettings
from ai4i_core.logging import get_logger

from consumers.notifications_consumer import email_templates

logger = get_logger(__name__)


@dataclass(frozen=True)
class Recipient:
    """One recipient exactly as the envelope carries it — email plus a
    display name to greet by. No user_id, no per-recipient DB lookup here
    or anywhere else in this consumer."""

    email: str
    display_name: str


# Belt-and-braces on top of EmailSettings.smtp_timeout (which aiosmtplib.send
# is given directly): a hung DNS lookup or a silently-dropped TCP connect
# isn't guaranteed to be covered by the provider's own timeout, and this
# consumer's loop must not let one bad/unreachable recipient hang forever.
_DEADLINE_HEADROOM_S = 0.0


@lru_cache(maxsize=1)
def _client() -> EmailClient:
    settings = EmailSettings()
    return EmailClient(build_provider(settings))


@lru_cache(maxsize=1)
def _send_deadline_s() -> float:
    return EmailSettings().smtp_timeout + _DEADLINE_HEADROOM_S


async def send_one(
    *, recipient: Recipient, event_name: str, tenant_name: str, details: List[Any],
) -> bool:
    """True on a confirmed send. Never raises and never blocks past
    _send_deadline_s() — provider failures are logged and reported as False
    (EmailClient.send_safe), and a hang past the deadline is treated the
    same way, so one bad or unreachable recipient can't take the others
    (or the whole consumer) down with it."""
    deadline = _send_deadline_s()
    try:
        message = email_templates.render_email(
            to=recipient.email, recipient_name=recipient.display_name,
            event_name=event_name, tenant_name=tenant_name, details=details,
        )
        return await asyncio.wait_for(_client().send_safe(message), timeout=deadline)
    except asyncio.TimeoutError:
        logger.error(
            "Email send timed out after %.0fs — treating as failed | to=%s event_name=%s",
            deadline, recipient.email, event_name,
        )
        return False
    except Exception:
        logger.exception(
            "send_one failed before/during send | to=%s event_name=%s",
            recipient.email, event_name,
        )
        return False
