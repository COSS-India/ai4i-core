"""Ties the envelope's resolved recipients (who) to emailer.py (send).

Who receives a notification is decided entirely by the producer now
(ai4i_core.kafka.recipients, at publish time) — this module used to
re-resolve that itself from configs_notification_alert.recipient_roles
(recipients.resolve()). That column is kept on purpose (platform-core's
e2a4c6b8d0f2 — the Adopter Admin catalog UI's own recipient toggle still
lives there) but nothing on the consumer side reads it anymore. All that's
left to look up here is the tenant's institution_name for the email body.
"""
from __future__ import annotations

import asyncio
from typing import Any, List

from ai4i_core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from consumers.notifications_consumer import emailer
from consumers.notifications_consumer import recipients as recipients_lookup
from consumers.notifications_consumer.recipients import Recipient

logger = get_logger(__name__)


async def deliver(
    auth_db: AsyncSession, *, tenant_id: str, recipients: List[str], event_name: str,
    details: List[Any],
) -> str:
    """Returns "sent", "no_recipients", or "failed". "sent" only if at least
    one recipient's email actually went out. ``recipients`` is a plain list
    of already-resolved email addresses (ai4i_core.kafka.recipients); there
    is no per-recipient display name in the envelope, so every send greets
    generically ("there"), matching the fallback recipients.py always used
    for a user with no full_name on file."""
    people = [Recipient(email=email, display_name="there") for email in recipients]
    if not people:
        logger.warning(
            "No recipients for event_name=%s tenant_id=%s",
            event_name, tenant_id,
        )
        return "no_recipients"

    # One lookup for the whole fan-out, not one per recipient — every
    # recipient of the same event gets the same institution_name.
    institution_name = await recipients_lookup.fetch_institution_name(auth_db, tenant_id=tenant_id)

    # return_exceptions=True: one recipient raising (e.g. a missing details
    # key at render time) must not discard every other recipient's already-
    # decided outcome, nor propagate out of deliver() — a raise here would
    # skip mark_delivery entirely and wedge the ledger row at "sending"
    # (see handler.py's own try/except around this call for the same
    # concern at the next layer up). An exception counts as that
    # recipient's send having failed, nothing more.
    outcomes = await asyncio.gather(
        *(
            emailer.send_one(
                recipient=person, institution_name=institution_name, event_name=event_name,
                details=details,
            )
            for person in people
        ),
        return_exceptions=True,
    )
    for person, outcome in zip(people, outcomes):
        if isinstance(outcome, Exception):
            logger.error(
                "send_one raised for recipient=%s event_name=%s tenant_id=%s: %s",
                person.email, event_name, tenant_id, outcome, exc_info=outcome,
            )
    sent_ok = [o for o in outcomes if o is True]
    return "sent" if sent_ok else "failed"
