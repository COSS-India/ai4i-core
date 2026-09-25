"""Canonical delivery states for ledger_notification_alert.status.delivery.

The producer (libs/ai4i_core/ai4i_core/kafka/ledger.py) only ever writes
IN_PROGRESS — a fresh occurrence that hasn't been delivered yet. The
consumer (kafka-consumers/notifications_consumer) advances it through
SENDING (claimed, in flight) to a terminal state: SENT, FAILED, SKIPPED (a
channel with no sender built yet, e.g. Slack/WhatsApp), or NO_RECIPIENTS
(resolved to nobody). Single source of truth so producer and consumer never
drift on the literal spelling of these states.
"""

from enum import Enum


class DeliveryStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    NO_RECIPIENTS = "no_recipients"
