"""Ties the envelope's resolved recipients (who) to emailer.py (send).

Who receives a notification is decided entirely by the producer
(ai4i_core.kafka.recipients, at publish time) and travels with the message
as email and name. All that's left to look up here is the tenant's
institution_name for the email body.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ai4i_core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from consumers.notifications_consumer import emailer
from consumers.notifications_consumer import recipients as recipients_lookup
from consumers.notifications_consumer.recipients import Recipient

logger = get_logger(__name__)


async def deliver(
    auth_db: AsyncSession, *, tenant_id: str, recipients: List[Dict[str, Any]], event_name: str,
    details: List[Any], platform_level: bool = False, affected_service: str = "",
) -> str:
    """Returns "sent", "no_recipients", or "failed". "sent" only if at least
    one recipient's email actually went out. ``recipients`` are the
    envelope's already-resolved {"email", "name"} entries; a recipient with
    no name is greeted generically ("there"). platform_level (monitoring)
    alerts have no tenant, so no institution name is looked up.
    ``affected_service`` (monitoring only, "" otherwise) is already resolved
    by the handler and passed through unchanged."""
    people = [
        Recipient(email=r["email"], display_name=r.get("name") or "there")
        for r in recipients
        if r.get("email")
    ]
    if not people:
        logger.warning(
            "No recipients for event_name=%s tenant_id=%s",
            event_name, tenant_id,
        )
        return "no_recipients"

    # One lookup for the whole fan-out, not one per recipient — every
    # recipient of the same event gets the same institution_name.
    institution_name = (
        "" if platform_level else await recipients_lookup.fetch_institution_name(auth_db, tenant_id=tenant_id)
    )

    # return_exceptions=True: one recipient raising (e.g. a missing details
    # key at render time) must not discard every other recipient's already-
    # decided outcome, nor propagate out of deliver(). An exception counts
    # as that recipient's send having failed, nothing more.
    outcomes = await asyncio.gather(
        *(
            emailer.send_one(
                recipient=person, institution_name=institution_name, event_name=event_name,
                details=details, affected_service=affected_service,
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
