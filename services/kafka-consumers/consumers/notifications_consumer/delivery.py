"""Maps the envelope's recipients (who) and details (what) straight onto
emailer.py — no lookups, no dedup, no per-event branching.

Everything this consumer needs — who gets it, what tenant it's for, what
goes in the body — travels with the message now, resolved by the producer
before it ever published. This module doesn't decide any of it; it just
fans the send out to every recipient and reports whether at least one
actually went out.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ai4i_core.logging import get_logger

from consumers.notifications_consumer import emailer
from consumers.notifications_consumer.emailer import Recipient

logger = get_logger(__name__)


def _people(recipients: List[Dict[str, str]]) -> List[Recipient]:
    return [
        Recipient(email=r["email"], display_name=r.get("name") or "there")
        for r in recipients
        if r.get("email")
    ]


async def deliver(
    *, tenant_name: str, recipients: List[Dict[str, str]], event_name: str, details: List[Any],
) -> bool:
    """True if at least one recipient's email actually went out."""
    people = _people(recipients)
    if not people:
        logger.warning("No recipients for event_name=%s tenant_name=%s", event_name, tenant_name)
        return False

    # return_exceptions=True: one recipient raising must not discard every
    # other recipient's already-decided outcome, nor propagate out of
    # deliver() — an exception counts as that recipient's send having
    # failed, nothing more.
    outcomes = await asyncio.gather(
        *(
            emailer.send_one(
                recipient=person, event_name=event_name, tenant_name=tenant_name, details=details,
            )
            for person in people
        ),
        return_exceptions=True,
    )
    for person, outcome in zip(people, outcomes):
        if isinstance(outcome, Exception):
            logger.error(
                "send_one raised for recipient=%s event_name=%s: %s",
                person.email, event_name, outcome, exc_info=outcome,
            )
    return any(outcome is True for outcome in outcomes)
