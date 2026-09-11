"""Ties recipients.py (who) to emailer.py (send) — the replacement for an
earlier version of this module that called out to auth-service over HTTP.
Per design correction: there is no auth-service endpoint in this design: the
email goes directly from this consumer, using its own connection to
ai4iplatform_auth (recipients.py) and ai4i_core.email (emailer.py).
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ai4i_core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from consumers.notification_consumer import emailer, recipients

logger = get_logger(__name__)


async def deliver(
    auth_db: AsyncSession, *, tenant_id: str, roles: List[str], event_name: str, details: Dict[str, Any]
) -> str:
    """Returns "sent", "no_recipients", or "failed". "sent" only if at least
    one recipient's email actually went out — a role that resolves to nobody
    is recorded as no_recipients rather than silently swallowed."""
    people = await recipients.resolve(auth_db, tenant_id=tenant_id, roles=roles)
    if not people:
        logger.warning(
            "No recipients for event_name=%s tenant_id=%s roles=%s",
            event_name, tenant_id, roles,
        )
        return "no_recipients"

    # return_exceptions=True: one recipient raising (e.g. a missing details
    # key at render time) must not discard every other recipient's already-
    # decided outcome, nor propagate out of deliver() — a raise here would
    # skip mark_delivery entirely and wedge the ledger row at "sending"
    # (see handler.py's own try/except around this call for the same
    # concern at the next layer up). An exception counts as that
    # recipient's send having failed, nothing more.
    outcomes = await asyncio.gather(
        *(
            emailer.send_one(recipient=person, event_name=event_name, details=details)
            for person in people
        ),
        return_exceptions=True,
    )
    for person, outcome in zip(people, outcomes):
        if isinstance(outcome, Exception):
            logger.error(
                "send_one raised for recipient=%s event_name=%s tenant_id=%s: %s",
                person.user_id, event_name, tenant_id, outcome, exc_info=outcome,
            )
    sent_ok = [o for o in outcomes if o is True]
    return "sent" if sent_ok else "failed"
