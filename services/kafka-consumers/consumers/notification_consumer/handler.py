"""Message handler for notification_consumer.

DUMMY SCAFFOLD (AI4IDS-3026): no notification-processing logic yet. This
service/image needs to exist and be deployable ahead of the real design
landing (see the updated Notifications-and-Alerts diagram: End-point/
Inference -> Kafka Consumer Notification -> Send Email / Slack). This
handler only proves the loop wiring — it stores+commits every message it
sees without acting on it.

Replace the body with real dispatch once the design is final. Keep the
signature (a plain async function taking a confluent_kafka.Message, no
decorator) — see ARCHITECTURE.md §3 and consumers/payperuse_consumer/handler.py
for the pattern this follows.
"""
from __future__ import annotations

from ai4i_core.logging import get_logger
from confluent_kafka import Message

logger = get_logger(__name__)


async def handle_notification_event(msg: Message) -> None:
    """No-op placeholder. Logs and returns — returning means success (commit
    and move on), per the handler contract in ARCHITECTURE.md §7.1."""
    logger.info(
        "notification_consumer received message (no-op) | %s[%d]@%d",
        msg.topic(), msg.partition(), msg.offset(),
    )
