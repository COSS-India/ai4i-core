"""notifications_consumer — Kafka Consumer Notification.

Implements skills/notification-kafka-design/notification-kafka-design.md:
reads notification/alert events off TOPIC_NOTIFICATION and sends the email
directly (no auth-service call). Everything the email needs — recipients,
tenant_name, details — is resolved producer-side (ai4i_core.kafka's shared
pipeline) and travels in the v2 envelope; this consumer only maps it onto
the template and sends. See handler.py, emailer.py, email_templates.py and
failures.py for the pieces; this file is just the consume loop wiring.

The only database access is the default connection (ai4iplatform_core),
used to write notification_alert_failure_log rows for events that reached
no recipient (failures.py).

Consumer-side only — the producers (auth-service's admin-change endpoints,
and payperuse_consumer's producer half) are separate work, not built here.

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
from confluent_kafka import KafkaError, KafkaException, Message

from bootstrap.config import get_db_settings
from bootstrap.consumers import CommitMode, ManagedConsumer
from bootstrap.lifecycle import infra, shutdown_event
from consumers.notifications_consumer import config as cfg
from consumers.notifications_consumer.handler import handle_notification_event

logger = get_logger(__name__)

# Hardcoded, never read from settings, never overridable by environment
# (ARCHITECTURE.md §5). New group — chosen deliberately, not copied from an
# existing consumer's group id.
GROUP_ID = "notification-service"


def _usable(msg: Message) -> bool:
    """Error classification, mirroring payperuse_consumer's own _usable()
    (ARCHITECTURE.md §6.3) — only a fatal error, or _AUTO_OFFSET_RESET
    specifically, may take the process down.

    _AUTO_OFFSET_RESET means KAFKA_AUTO_OFFSET_RESET=error fired: this group
    has no valid committed offset and cannot proceed on its own. Left as a
    plain ERROR log (the old behaviour here) it repeats on every poll
    forever without ever processing a real message — logging loudly is not
    the same as failing loudly. Raising crashes the process so the
    orchestrator restarts it and an on-call engineer actually gets paged,
    instead of a consumer that looks alive while doing nothing.
    """
    err = msg.error()
    if err is None:
        return True

    if err.code() == KafkaError._PARTITION_EOF:
        return False  # informational, not a failure

    if err.code() == KafkaError._AUTO_OFFSET_RESET or err.fatal():
        logger.critical(
            "Fatal Kafka error — exiting for restart | code=%s: %s", err.name(), err.str()
        )
        raise KafkaException(err)

    logger.error("Kafka error entry | code=%s: %s", err.name(), err.str())
    return False


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
                        # %s, not %d: this fence runs before _usable() below,
                        # so an error/EOF sentinel message (msg.offset() is
                        # None for those — confirmed in staging) can reach
                        # here too, not just real data messages. %d on a
                        # None crashed the format call itself (TypeError
                        # inside logger.warning, caught and printed by
                        # logging's own handleError — non-fatal to this
                        # loop, but the intended log line was lost).
                        logger.warning(
                            "Skipping message from revoked partition | %s[%s]@%s",
                            msg.topic(), msg.partition(), msg.offset(),
                        )
                        continue

                    if not _usable(msg):
                        continue

                    await handle_notification_event(msg)
                    await consumer.record_processed(msg)
        finally:
            consumer.shutdown()
