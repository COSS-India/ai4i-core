"""Message handler for notification_consumer — design doc §8's step-by-step,
implemented.

Consumer-side only: this reads whatever envelope (design doc §4) a producer
publishes and acts on it. Nothing here publishes to Kafka — the 5 admin-
change endpoints and payperuse_consumer's producer side are separate work.

Retry behaviour on a handler failure is a design doc open question (§12),
not decided here — a per-message exception is logged and the message is
treated as handled (committed), not redelivered. That matches this
consumer's own send-side retries already being bounded (emailer.py's
EmailClient.send_safe) rather than adding a second, undecided retry ladder
on top.

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
from consumers.notification_consumer import delivery, ledger, patterns
from consumers.notification_consumer.catalog_cache import NotificationConfig, get_config

logger = get_logger(__name__)


def _parse_envelope(msg: Message) -> Optional[Dict[str, Any]]:
    """design doc §4's 5 fields, plus the optional actor_id §5 assumes.
    Malformed input is a permanent skip, not a retry — there is no version
    of this message that will parse differently later."""
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

            # design doc §8, step 3 — one gate, before any per-channel work.
            if not cfg.is_enabled:
                return
            enabled_roles = [role for role, on in cfg.recipient_roles.items() if on]
            if not enabled_roles:
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
    current_status = await ledger.fetch_current_status(
        db,
        notification_id=cfg.id,
        tenant_id=envelope["tenant_id"],
        subject=envelope["subject"],
        channel=channel,
    )
    decision = patterns.decide(
        event_name=envelope["event_name"],
        current_status=current_status,
        occurred_at=envelope["occurred_at"],
        details=envelope["details"],
        thresholds=cfg.thresholds,
    )
    if decision.new_status is None:
        return  # nothing changed — design doc §6/§8

    row_id = await ledger.claim(
        db,
        notification_id=cfg.id,
        tenant_id=envelope["tenant_id"],
        subject=envelope["subject"],
        channel=channel,
        new_status=decision.new_status,
        guard=decision.guard,
        actor_id=envelope.get("actor_id"),
    )
    if row_id is None:
        return  # lost the race, or the guard correctly rejected a stale write — design doc §7

    if not decision.should_send:
        return  # a reset to {} — nothing to deliver

    if channel != "EMAIL":
        # Slack/WhatsApp sending isn't built yet — design doc §8's "Templates
        # folder" note and §12's open questions. The claim above still stands
        # (this band/occurrence is recorded), so switching the channel on
        # later won't be suppressed by an email row that already fired.
        await ledger.mark_delivery(db, row_id=row_id, delivery="skipped")
        return

    async with session_scope(name="auth") as auth_db:
        outcome = await delivery.deliver(
            auth_db,
            tenant_id=envelope["tenant_id"],
            roles=enabled_roles,
            event_name=envelope["event_name"],
            details=envelope["details"],
        )
    await ledger.mark_delivery(db, row_id=row_id, delivery="sent" if outcome == "sent" else "failed")
