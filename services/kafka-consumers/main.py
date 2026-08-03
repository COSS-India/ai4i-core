import asyncio
import signal

from confluent_kafka import KafkaException, TopicPartition
from confluent_kafka.aio import AIOConsumer

from ai4i_core.bootstrap import init_redis
from ai4i_core.logging import configure_logging, get_logger

configure_logging(service_name="aiokafka-consumer")

import consumers.payperuse_consumer  # noqa: F401 — side-effect import: populates TOPIC_REGISTRY
from config import settings, build_consumer_config
from consumers.registry import KafkaRegistry, TOPIC_REGISTRY
from db_registry import db_registry, init_databases

logger = get_logger(__name__)

# ===============
# DO NOT CHANGE: this is only 1 process that does lightweight io bound consumer tasks only,
# do not change, do not make it configurable, do not push it to settings
KAFKA_GROUP_ID = "aio-python-consumers"
# ===============

# Commit offsets every N successful messages, or every T seconds since the
# last commit — whichever comes first — instead of after every message. A
# broker round-trip per message is real overhead under burst load; batching
# is safe here because handle_ppu_usage is already redelivery-safe (see the
# Redis dedup check) — a crash mid-batch just means up to COMMIT_BATCH_SIZE
# already-billed messages get redelivered and no-op'd on restart, not
# double-billed.
#
# Tracked per (topic, partition) — NOT a single shared "last message" — and
# committed via explicit TopicPartition offsets, not a bare consumer.commit().
# A single shared last-message was tried first and is WRONG for a
# multi-partition topic: commit(message=msg) only advances msg's own
# partition, so with messages interleaving across partitions, whichever
# partition owned the most-recently-processed message got committed and the
# rest never advanced at all — reproduced locally against an 8-partition
# topic (7 of 8 partitions never committed a single offset). A bare
# consumer.commit() (no explicit offsets) isn't a safe fix either:
# enable.auto.offset.store defaults to true, so poll() auto-marks a
# message's offset as committable the instant it's returned — including
# messages whose processing later raised — a bare commit() would then
# commit past a failed message anyway. Explicit per-partition offsets, only
# updated after a message's dispatch() succeeds, avoid both problems.
COMMIT_BATCH_SIZE = 100
COMMIT_INTERVAL_S = 5.0

async def main() -> None:
    # ── Database registry ──
    db_cfg = settings.db_settings
    logger.info(
        "Initialising database registry | host=%s port=%d pool_size=%d max_overflow=%d"
        " platform_core_db=%s",
        db_cfg.POSTGRES_HOST,
        db_cfg.POSTGRES_PORT,
        db_cfg.DB_POOL_SIZE,
        db_cfg.DB_MAX_OVERFLOW,
        db_cfg.PLATFORM_CORE_DB,
    )
    try:
        await init_databases(db_cfg)
    except Exception as exc:
        logger.critical("Failed to initialise database registry | error=%s", exc)
        raise

    logger.info(
        "Database registry ready | count=%d registered=%s",
        len(db_registry.names()),
        db_registry.names(),
    )

    # ── Redis ──
    redis_cfg = settings.redis_settings
    logger.info(
        "Redis settings loaded | host=%s port=%d db=%d timeout=%ds max_connections=%d",
        redis_cfg.REDIS_HOST,
        redis_cfg.REDIS_PORT,
        redis_cfg.REDIS_DB,
        redis_cfg.REDIS_TIMEOUT,
        redis_cfg.REDIS_MAX_CONNECTIONS,
    )

    try:
        await init_redis(settings.redis_settings.get_redis_url())
    except Exception as exc:
        logger.critical("Failed to initialise redis connection| error=%s", exc)
        raise

    # ── Kafka ──
    registry = KafkaRegistry(TOPIC_REGISTRY)
    logger.info(
        "Kafka registry ready | broker=%s group_id=%s topics=%s",
        settings.KAFKA_SERVER,
        KAFKA_GROUP_ID,
        registry.topics(),
    )

    consumer = AIOConsumer(build_consumer_config(KAFKA_GROUP_ID, settings))

    try:
        await consumer.subscribe(registry.topics())
    except KafkaException as exc:
        logger.critical("Failed to subscribe to Kafka topics: %s", exc)
        raise

    logger.info(
        "Consumer started | topics=%s poll_timeout=%.1fs auto_offset_reset=%s",
        registry.topics(),
        settings.KAFKA_POLL_TIMEOUT_S,
        settings.KAFKA_AUTO_OFFSET_RESET,
    )

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    # (topic, partition) -> next offset to commit (last successfully
    # processed message's offset + 1 — matching the +1 convention
    # consumer.commit(message=msg) applies automatically, which committing
    # via explicit TopicPartition offsets does NOT do for us.
    pending_offsets: dict[tuple[str, int], int] = {}
    uncommitted = 0
    last_commit_time = loop.time()

    async def _flush_commit() -> None:
        nonlocal uncommitted, last_commit_time, pending_offsets
        if not pending_offsets:
            return
        offsets = [
            TopicPartition(topic, partition, offset)
            for (topic, partition), offset in pending_offsets.items()
        ]
        await consumer.commit(offsets=offsets)
        pending_offsets = {}
        uncommitted = 0
        last_commit_time = loop.time()

    async with consumer:
        while not shutdown.is_set():
            try:
                msg = await consumer.poll(timeout=settings.KAFKA_POLL_TIMEOUT_S)
            except KafkaException as exc:
                logger.error("Poll failed: %s", exc)
                continue

            if msg is None:
                # Nothing to process right now — flush any pending commit so
                # offsets aren't held back indefinitely during quiet periods.
                if loop.time() - last_commit_time >= COMMIT_INTERVAL_S:
                    await _flush_commit()
                continue
            if msg.error():
                logger.error("Kafka error: %s", msg.error())
                continue

            try:
                await registry.dispatch(msg.topic(), msg)
            except Exception as exc:
                logger.exception(
                    "Unhandled error dispatching message from topic %s: %s",
                    msg.topic(),
                    exc,
                )
                # Don't count a failed message toward the batch — its offset
                # must stay uncommitted so it's redelivered on restart.
                continue

            pending_offsets[(msg.topic(), msg.partition())] = msg.offset() + 1
            uncommitted += 1
            if uncommitted >= COMMIT_BATCH_SIZE or loop.time() - last_commit_time >= COMMIT_INTERVAL_S:
                await _flush_commit()

        # Flush any remaining uncommitted offsets before shutting down.
        await _flush_commit()

    logger.info("Shutdown signal received — draining database connections")
    await db_registry.close_all()
    logger.info("Consumer shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
