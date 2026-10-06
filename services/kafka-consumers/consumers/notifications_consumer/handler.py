"""Message handler for notifications_consumer: map the envelope onto the
email template and send it. Nothing else.

The producer (ai4i_core.kafka's shared pipeline) already decided the event
is new, claimed its ledger row, and resolved the recipients (email and
name), the tenant_name and the positional details before publishing. This
handler does not read or write the ledger and does no lookups of its own.

A Kafka redelivery of the same event (a crash or rebalance between handling
and the offset commit) is caught by a Redis claim on its event_id (SET NX),
taken before sending. Redis being unavailable, or an envelope without an
event_id, does not block delivery: a rare duplicate email beats a lost one.

An event counts as delivered when the email reached at least one
recipient. When it did not — malformed message, no channel this consumer
sends on, or every send failed — one row goes to
notification_alert_failure_log (failures.py). The message is then treated as
handled (committed), not redelivered: the send-side retries are already
bounded (emailer.py). The row carries the first recipient's error, so a
render failure (the producer sent too few details) reads differently from
an SMTP outage.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping, Optional, Tuple

from ai4i_core.bootstrap import get_redis_client
from ai4i_core.kafka import FailureCode, NotificationChannel, Operation
from ai4i_core.logging import get_logger
from confluent_kafka import Message

from consumers.notifications_consumer import emailer, failures
from consumers.notifications_consumer.config import Constants

logger = get_logger(__name__)

# The one channel this consumer sends on (Slack/WhatsApp aren't built).
EMAIL = NotificationChannel.EMAIL.value


async def _claim(event_id: Any) -> bool:
    """True when this is the first delivery of event_id."""
    if not event_id:
        return True
    try:
        return bool(
            await get_redis_client().set(
                f"{Constants.DELIVERY_CLAIM_KEY_PREFIX}{event_id}", "1",
                nx=True, ex=Constants.DELIVERY_CLAIM_TTL_SECONDS,
            )
        )
    except Exception as exc:
        logger.warning("Delivery claim unavailable — delivering without dedup | event_id=%s: %s", event_id, exc)
        return True


_Failure = Tuple[FailureCode, str, Optional[BaseException]]


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}" if str(error) else type(error).__name__


async def _deliver(envelope: Mapping[str, Any]) -> Optional[_Failure]:
    """None when the email reached at least one recipient, else why not:
    (code, message, the first recipient's error)."""
    channels = envelope.get("channels") or []
    if EMAIL not in channels:
        return FailureCode.NO_SUPPORTED_CHANNEL, f"no supported channel in {channels!r}; only {EMAIL} is sent", None

    recipients = envelope.get("recipients") or []
    errors = await asyncio.gather(
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
    if any(error is None for error in errors):
        return None
    message = f"email reached 0 of {len(recipients)} recipient(s)"
    if not errors:
        return FailureCode.EMAIL_SEND_FAILED, message, None
    return FailureCode.EMAIL_SEND_FAILED, f"{message}; first error: {_describe(errors[0])}", errors[0]


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

    if not await _claim(envelope.get("event_id")):
        logger.info("Redelivery of an already handled event — skipping | event_id=%s", envelope.get("event_id"))
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

    code, message, error = failure
    logger.error(
        "Notification not delivered | event_id=%s event_name=%s tenant_id=%s: %s",
        envelope.get("event_id"), envelope.get("event_name"), envelope.get("tenant_id"), message,
    )
    await failures.record(envelope, code, kafka_topic=topic, message=message, error=error)
