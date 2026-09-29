"""Message handler for notifications_consumer: map the envelope onto the
email template and send it. Nothing else.

The producer (ai4i_core.kafka's shared pipeline) already decided the event
is new, claimed its ledger row, and resolved the recipients (email and
name), the tenant_name and the positional details before publishing. This
handler does not dedup, does not read or write the ledger, and does no
lookups of its own.

An event counts as delivered when the email reached at least one
recipient. When it did not — malformed message, no channel this consumer
sends on, or every send failed — one row goes to
notification_alert_failure_log (failures.py). The message is then treated as
handled (committed), not redelivered: the send-side retries are already
bounded (emailer.py, EmailClient.send_safe).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping, Optional, Tuple

from ai4i_core.kafka import FailureCode, NotificationChannel, Operation
from ai4i_core.logging import get_logger
from confluent_kafka import Message

from consumers.notifications_consumer import emailer, failures

logger = get_logger(__name__)

# The one channel this consumer sends on (Slack/WhatsApp aren't built).
EMAIL = NotificationChannel.EMAIL.value


async def _deliver(envelope: Mapping[str, Any]) -> Optional[Tuple[FailureCode, str]]:
    """None when the email reached at least one recipient, else why not."""
    channels = envelope.get("channels") or []
    if EMAIL not in channels:
        return FailureCode.NO_SUPPORTED_CHANNEL, f"no supported channel in {channels!r}; only {EMAIL} is sent"

    recipients = envelope.get("recipients") or []
    sent = await asyncio.gather(
        *(
            emailer.send(
                recipient=recipient,
                event_name=envelope.get("event_name"),
                tenant_name=envelope.get("tenant_name"),
                details=envelope.get("details") or [],
            )
            for recipient in recipients
        )
    )
    if any(sent):
        return None
    return FailureCode.EMAIL_SEND_FAILED, f"email reached 0 of {len(recipients)} recipient(s)"


async def handle_notification_event(msg: Message) -> None:
    topic = msg.topic()
    try:
        envelope = json.loads(msg.value())
        if not isinstance(envelope, dict):
            raise ValueError("envelope is not a JSON object")
    except (TypeError, ValueError) as exc:
        logger.error("Malformed notification message | %s[%s]@%s: %s", topic, msg.partition(), msg.offset(), exc)
        await failures.record(
            {}, FailureCode.INVALID_ENVELOPE, kafka_topic=topic, operation=Operation.VALIDATE, error=exc,
        )
        return

    try:
        failure = await _deliver(envelope)
    except Exception as exc:
        logger.exception("Delivery raised | event_id=%s", envelope.get("event_id"))
        await failures.record(envelope, FailureCode.EMAIL_SEND_FAILED, kafka_topic=topic, error=exc)
        return

    if failure is None:
        logger.info(
            "Notification delivered | event_id=%s event_name=%s tenant_id=%s",
            envelope.get("event_id"), envelope.get("event_name"), envelope.get("tenant_id"),
        )
        return

    code, message = failure
    logger.error(
        "Notification not delivered | event_id=%s event_name=%s tenant_id=%s: %s",
        envelope.get("event_id"), envelope.get("event_name"), envelope.get("tenant_id"), message,
    )
    await failures.record(envelope, code, kafka_topic=topic, message=message)
