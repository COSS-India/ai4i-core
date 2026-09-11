"""notification_consumer — Kafka Consumer Notification.

Implements skills/notification-kafka-design/notification-kafka-design.md:
reads notification/alert events off TOPIC_NOTIFICATION, decides whether each
one needs an email per the notification's saved settings and per-tenant
history, and sends it directly (no auth-service call). See catalog_cache.py,
patterns.py, ledger.py, recipients.py, emailer.py, delivery.py and
handler.py for the pieces; this file is just the consume loop wiring, plus
opening the second (auth) database connection recipients.py depends on.

Consumer-side only — the producers (5 admin-change endpoints, and
payperuse_consumer's producer half) are separate work, not built here.

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
from bootstrap.lifecycle import add_database, infra, shutdown_event
from consumers.notification_consumer import config as cfg, pii_crypto
from consumers.notification_consumer.handler import handle_notification_event

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

    # Hand the key to pii_crypto explicitly — pydantic-settings loads .env
    # into `settings`, not into os.environ, so a bare os.getenv() inside
    # pii_crypto would never see it. Mirrors auth-service's own
    # config.py -> pii_crypto.configure_key() handoff exactly.
    pii_crypto.configure_key(
        settings.PII_ENCRYPTION_KEY.get_secret_value() if settings.PII_ENCRYPTION_KEY else None
    )

    async with infra(db_name=db.PLATFORM_CORE_DB):
        # Second connection, named "auth" — recipients.py resolves who holds
        # which role for a tenant by reading ai4iplatform_auth directly.
        # Opened once here, not per-message; infra()'s own teardown closes
        # every named connection alongside the default one.
        await add_database("auth", db_name=settings.AUTH_SERVICE_DB)

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

                    if not _usable(msg):
                        continue

                    await handle_notification_event(msg)
                    await consumer.record_processed(msg)
        finally:
            consumer.shutdown()
