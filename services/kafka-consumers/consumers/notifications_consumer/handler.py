"""Message handler for notifications_consumer.

Deliberately dumb, per review: this consumer does not decide whether a
notification is new, does not touch ledger_notification_alert, does not
read configs_notification_alert, and does not query ai4iplatform_auth for
anything. All of that already happened producer-side. This handler's only
job is: map the envelope onto an email and trigger the send. If nothing
went out — to anyone, for any reason, including a malformed envelope —
the entire raw message is recorded, verbatim, in notification_failures
(failures.py) and nothing more is inferred about why.

EMAIL is the only channel this consumer implements (Slack/WhatsApp were
never built) — see main.py's module docstring for the producer-facing
callout on what adding channel selection would need.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ai4i_core.logging import get_logger
from confluent_kafka import Message

from bootstrap.lifecycle import session_scope
from consumers.notifications_consumer import delivery, failures

logger = get_logger(__name__)

CHANNEL = "EMAIL"


def _parse_envelope(raw: bytes) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None

    event_name = data.get("event_name")
    recipients = data.get("recipients") or []
    if not event_name or not recipients:
        return None

    return {
        "event_name": event_name,
        # Sent by the producer now — this consumer no longer looks up a
        # tenant's own name from ai4iplatform_auth.
        "tenant_name": data.get("tenant_name") or "",
        # A plain, positional array, rendered as-is — see email_templates.py.
        "details": data.get("details") or [],
        # [{"email": ..., "name": ...}, ...] — already resolved and
        # decrypted by the producer.
        "recipients": recipients,
    }


async def handle_notification_event(msg: Message) -> None:
    raw = msg.value()
    envelope = _parse_envelope(raw)
    delivered = False
    if envelope is not None:
        try:
            delivered = await delivery.deliver(
                tenant_name=envelope["tenant_name"],
                recipients=envelope["recipients"],
                event_name=envelope["event_name"],
                details=envelope["details"],
            )
        except Exception:
            logger.exception("Unhandled error delivering notification event | raw=%r", raw)
            delivered = False

    if delivered:
        logger.info("Notification delivered | channel=%s", CHANNEL)
        return

    logger.error("Notification delivery failed | channel=%s", CHANNEL)
    try:
        async with session_scope() as db:
            await failures.record_failure(db, message=raw, channel=CHANNEL)
    except Exception:
        logger.exception("Failed to record notification_failures row | raw=%r", raw)
