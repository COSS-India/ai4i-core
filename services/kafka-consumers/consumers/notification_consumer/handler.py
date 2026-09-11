"""Message handler for notification_consumer.

The producer (auth-service / platform-core-service / payperuse_consumer)
already decided whether this occurrence is new and claimed the ledger row
before ever publishing — see libs/ai4i_core/ai4i_core/kafka/ledger.py. By
the time a message reaches here, ledger_notification_alert already has a
row for (notification_id, tenant_id, subject, channel) with
{"value": ..., "delivery": "in_progress"}. This handler does not decide a
new value; it claims the SEND (ledger.claim_send), delivers, and settles
`delivery` to "sent"/"failed".

Consumer-side only: this reads whatever envelope a producer publishes and
acts on it. Nothing here publishes to Kafka.

Retry behaviour on a handler failure is a design doc open question (§12),
not decided here — a per-message exception is logged and the message is
treated as handled (committed), not redelivered. That matches this
consumer's own send-side retries already being bounded (emailer.py's
EmailClient.send_safe / the deadline around it) rather than adding a
second, undecided retry ladder on top.

Two database connections are in play: the default one (ai4iplatform_core —
settings, ledger) and a second, named one opened once at startup (main.py)
against ai4iplatform_auth, for recipients.py to resolve who actually gets
the email — see delivery.py.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ai4i_core.logging import get_logger
from confluent_kafka import Message

from bootstrap.lifecycle import session_scope
from consumers.notification_consumer import delivery, ledger
from consumers.notification_consumer.catalog_cache import NotificationConfig, get_config

logger = get_logger(__name__)

# Terminal delivery states — a row already settled here needs nothing more
# from a redelivered/duplicate message.
_TERMINAL_DELIVERIES = {"sent", "failed", "skipped"}


def _parse_envelope(msg: Message) -> Optional[Dict[str, Any]]:
    """The 5-field envelope publish_event() (ai4i_core.kafka.producer)
    sends, plus actor_id. Malformed input is a permanent skip, not a
    retry — there is no version of this message that will parse
    differently later."""
    try:
        data = json.loads(msg.value())
    except (TypeError, ValueError) as exc:
        logger.error(
            "Malformed message — not valid JSON | %s[%d]@%d: %s",
            msg.topic(), msg.partition(), msg.offset(), exc,
        )
        return None

    event_name = data.get("event_name")
    tenant_id = data.get("tenant_id")
    if not event_name or not tenant_id:
        logger.error("Malformed message — missing event_name/tenant_id | %r", data)
        return None

    return {
        "event_name": event_name,
        "tenant_id": str(tenant_id),
        "occurred_at": data.get("occurred_at") or "",
        "subject": data.get("subject") or {},
        "details": data.get("details") or {},
        "actor_id": data.get("actor_id"),
    }


async def handle_notification_event(msg: Message) -> None:
    envelope = _parse_envelope(msg)
    if envelope is None:
        return

    try:
        async with session_scope() as db:
            cfg = await get_config(db, envelope["event_name"])
            if cfg is None:
                logger.warning(
                    "No catalog row for event_name=%s — skipping", envelope["event_name"]
                )
                return

            # The producer already checked this before publishing
            # (is_notification_enabled) — re-checking here is cheap
            # insurance against a stale/racing config read, not the
            # primary gate.
            enabled_roles = [role for role, on in cfg.recipient_roles.items() if on]
            if not enabled_roles:
                logger.info(
                    "Gated — no recipient_roles enabled for event_name=%s tenant_id=%s",
                    envelope["event_name"], envelope["tenant_id"],
                )
                return

            for channel in cfg.channels:
                await _process_channel(db, cfg, envelope, channel, enabled_roles)
    except Exception:
        logger.exception(
            "Unhandled error processing notification event | event_name=%s tenant_id=%s",
            envelope["event_name"], envelope["tenant_id"],
        )


async def _process_channel(
    db, cfg: NotificationConfig, envelope: Dict[str, Any], channel: str, enabled_roles: List[str]
) -> None:
    row = await ledger.fetch_row(
        db,
        notification_id=cfg.id,
        tenant_id=envelope["tenant_id"],
        subject=envelope["subject"],
        channel=channel,
    )
    if row is None:
        logger.warning(
            "No ledger row yet for event_name=%s tenant_id=%s channel=%s — "
            "producer hasn't committed its claim, or this channel wasn't "
            "configured when it published. Nothing to do.",
            envelope["event_name"], envelope["tenant_id"], channel,
        )
        return

    row_id, status = row
    current_delivery = status.get("delivery")
    if current_delivery in _TERMINAL_DELIVERIES:
        return  # already handled — a genuine redelivery of this exact occurrence

    if current_delivery != "in_progress":
        logger.warning(
            "Unexpected delivery state %r on ledger row %s — leaving it alone",
            current_delivery, row_id,
        )
        return

    if channel != "EMAIL":
        # Slack/WhatsApp sending isn't built yet — design doc §8's "Templates
        # folder" note and §12's open questions.
        await ledger.mark_delivery(db, row_id=row_id, delivery="skipped")
        return

    won = await ledger.claim_send(db, row_id=row_id)
    if not won:
        return  # a concurrent redelivery/replica already claimed this send

    async with session_scope(name="auth") as auth_db:
        outcome = await delivery.deliver(
            auth_db,
            tenant_id=envelope["tenant_id"],
            roles=enabled_roles,
            event_name=envelope["event_name"],
            details=envelope["details"],
        )
    delivery_status = "sent" if outcome == "sent" else "failed"
    await ledger.mark_delivery(db, row_id=row_id, delivery=delivery_status)
    logger.info(
        "Notification delivery settled | event_name=%s tenant_id=%s channel=%s "
        "ledger_id=%s outcome=%s delivery=%s",
        envelope["event_name"], envelope["tenant_id"], channel, row_id, outcome, delivery_status,
    )
