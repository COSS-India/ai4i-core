"""Message handler for notifications_consumer.

The producer (auth-service / platform-core-service / payperuse_consumer,
through ai4i_core.kafka's shared pipeline) already decided the occurrence is
new, claimed its ledger row and resolved who gets it before publishing. The
envelope (schema_version 2) carries everything delivery needs: the channels,
the recipients (email and name) and the positional details. This handler
only delivers.

A Kafka redelivery of the same event is caught by a Redis claim on its
event_id (SET NX), taken before sending. Redis being unavailable does not
block delivery: a rare duplicate email beats a lost one.

Consumer-side only: nothing here publishes to Kafka. A per-message
exception is logged and the message is treated as handled (committed), not
redelivered — this consumer's own send-side retries are already bounded
(emailer.py's EmailClient.send_safe).

Two database connections are in play: the default one (ai4iplatform_core)
and a second, named one opened once at startup (main.py) against
ai4iplatform_auth, for recipients.py's fetch_institution_name() — see
delivery.py.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ai4i_core.bootstrap import get_redis_client
from ai4i_core.kafka import NotificationChannel, NotificationType
from ai4i_core.kafka.constants import ENVELOPE_SCHEMA_VERSION, SubjectKey
from ai4i_core.logging import get_logger
from confluent_kafka import Message

from bootstrap.lifecycle import session_scope
from consumers.notifications_consumer import delivery
from consumers.notifications_consumer import recipients as recipients_lookup
from consumers.notifications_consumer.config import Constants

logger = get_logger(__name__)


def _parse_envelope(msg: Message) -> Optional[Dict[str, Any]]:
    """The v2 envelope ai4i_core.kafka's publisher sends. Malformed input is
    a permanent skip, not a retry — there is no version of this message
    that will parse differently later."""
    try:
        data = json.loads(msg.value())
    except (TypeError, ValueError) as exc:
        logger.error(
            "Malformed message — not valid JSON | %s[%d]@%d: %s",
            msg.topic(), msg.partition(), msg.offset(), exc,
        )
        return None
    if not isinstance(data, dict):
        logger.error("Malformed message — not a JSON object | %r", data)
        return None

    if data.get("schema_version") != ENVELOPE_SCHEMA_VERSION:
        logger.error(
            "Unsupported envelope schema_version=%r (expected %d) | event_name=%r",
            data.get("schema_version"), ENVELOPE_SCHEMA_VERSION, data.get("event_name"),
        )
        return None

    event_id = data.get("event_id")
    event_name = data.get("event_name")
    tenant_id = data.get("tenant_id")
    if not event_id or not event_name or not tenant_id:
        logger.error("Malformed message — missing event_id/event_name/tenant_id | %r", data)
        return None

    return {
        "event_id": str(event_id),
        "event_name": event_name,
        "notification_type": data.get("notification_type"),
        "tenant_id": str(tenant_id),
        "channels": data.get("channels") or [],
        # A plain positional array — each event_name has its own fixed value
        # order, matching the email_templates.py renderer emailer.py calls.
        "details": data.get("details") or [],
        # Ledger subject; for MONITORING events it carries the service_id
        # (ai4i_core.kafka.keys.monitoring_subject) — the "Affected Service".
        "subject": data.get("subject") if isinstance(data.get("subject"), dict) else {},
        # [{"email": ..., "name": ...}], resolved by the producer.
        "recipients": [r for r in data.get("recipients") or [] if isinstance(r, dict) and r.get("email")],
    }


async def _claim(event_id: str) -> bool:
    """True when this delivery is the first for event_id."""
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


async def _affected_service(envelope: Dict[str, Any]) -> str:
    """The monitoring email's "Affected Service": the service's name, from the
    envelope subject's service_id. "" for non-MONITORING events or a
    monitoring event with no service_id — the template then omits the line.
    A lookup failure degrades to the raw service_id rather than losing the
    email (the default connection is ai4iplatform_core, where mm_services is)."""
    if envelope["notification_type"] != NotificationType.MONITORING.value:
        return ""
    service_id = str(envelope["subject"].get(SubjectKey.SERVICE_ID.value) or "").strip()
    if not service_id:
        return ""
    try:
        async with session_scope() as core_db:
            return await recipients_lookup.fetch_service_name(core_db, service_id=service_id)
    except Exception as exc:
        logger.warning("Service name lookup failed — using raw service_id=%s: %s", service_id, exc)
        return service_id


async def handle_notification_event(msg: Message) -> None:
    envelope = _parse_envelope(msg)
    if envelope is None:
        return

    if NotificationChannel.EMAIL.value not in envelope["channels"]:
        # Slack/WhatsApp sending isn't built yet.
        logger.info(
            "No supported channel — skipping | event_name=%s channels=%s",
            envelope["event_name"], envelope["channels"],
        )
        return

    if not await _claim(envelope["event_id"]):
        return  # a redelivery of an event already handled

    try:
        affected_service = await _affected_service(envelope)
        async with session_scope(name="auth") as auth_db:
            outcome = await delivery.deliver(
                auth_db,
                tenant_id=envelope["tenant_id"],
                recipients=envelope["recipients"],
                event_name=envelope["event_name"],
                details=envelope["details"],
                platform_level=envelope["notification_type"] == NotificationType.MONITORING.value,
                affected_service=affected_service,
            )
    except Exception:
        logger.exception(
            "Delivery raised | event_id=%s event_name=%s tenant_id=%s",
            envelope["event_id"], envelope["event_name"], envelope["tenant_id"],
        )
        return
    logger.info(
        "Notification delivered | event_id=%s event_name=%s tenant_id=%s outcome=%s",
        envelope["event_id"], envelope["event_name"], envelope["tenant_id"], outcome,
    )
