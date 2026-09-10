"""notification_consumer — DUMMY SCAFFOLD (AI4IDS-3026).

No real logic yet. This exists purely so `kafka-consumers` can be built and
deployed as a `--consumer notification_consumer` process ahead of the
Notifications-and-Alerts design landing (see the updated diagram: an
End-point/Inference event reaches a Kafka consumer that checks the saved
notification config and fans out to Send Email / Slack). handler.py is a
no-op; replace it once that design is final.

Built on bootstrap/ (ManagedConsumer + lifecycle), the shipped shape new
consumers should copy — unlike payperuse_consumer, which predates bootstrap/
and is not the shape to copy wholesale (see README's "Adding a consumer").

GROUP_ID is a brand-new group: KAFKA_AUTO_OFFSET_RESET must be set to
`error` in this consumer's own environment before first start (README
"Adding a consumer" step 5 / ARCHITECTURE.md §10) — do not inherit
`earliest` from a shared .env meant for another consumer.
"""
from __future__ import annotations

from ai4i_core.logging import get_logger
from confluent_kafka import KafkaException

from bootstrap.config import get_db_settings
from bootstrap.consumers import CommitMode, ManagedConsumer
from bootstrap.lifecycle import infra, shutdown_event
from consumers.notification_consumer import config as cfg
from consumers.notification_consumer.handler import handle_notification_event

logger = get_logger(__name__)

# Hardcoded, never read from settings, never overridable by environment
# (ARCHITECTURE.md §5). New group — chosen deliberately, not copied from an
# existing consumer's group id.
GROUP_ID = "notification-service"


async def run() -> None:
    db = get_db_settings()
    settings = cfg.get_settings()

    async with infra(db_name=db.PLATFORM_CORE_DB):
        consumer = ManagedConsumer.build_bulk_message_consumer(
            group_id=GROUP_ID,
            topic=settings.TOPIC_NOTIFICATION,
            # Explicit, not defaulted — see ManagedConsumer.CommitMode's docstring.
            commit_mode=CommitMode.PER_MESSAGE,
        )

        shutdown = shutdown_event()
        logger.info(
            "Consumer started | group_id=%s topic=%s batch_size=%d commit_mode=%s",
            GROUP_ID, settings.TOPIC_NOTIFICATION,
            consumer.batch_size, consumer.commit_mode.value,
        )
        try:
            while not shutdown.is_set():
                try:
                    chunk = await consumer.consume_batch()
                except KafkaException as exc:
                    # Only a fatal error may take the process down; anything
                    # else is logged and retried by the next iteration.
                    if exc.args[0].fatal():
                        raise
                    logger.error("Fetch failed | code=%s: %s", exc.args[0].name(), exc.args[0].str())
                    continue

                for msg in chunk:
                    # ── the §6.4 fence, before anything else ──
                    # A rebalance can revoke a partition while its messages are
                    # still in this chunk.
                    if not consumer.owns(msg):
                        logger.warning(
                            "Skipping message from revoked partition | %s[%d]@%d",
                            msg.topic(), msg.partition(), msg.offset(),
                        )
                        continue

                    if msg.error() is not None:
                        logger.error("Kafka error entry | %s", msg.error().str())
                        continue

                    await handle_notification_event(msg)
                    await consumer.record_processed(msg)
        finally:
            consumer.shutdown()
