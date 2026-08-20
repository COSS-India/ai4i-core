"""payperuse_consumer — bills ai-inference spans against tenant wallets.

Owns its own process: its group id, its topic subscription, its lifecycle and
its poll loop. Launched by the service-root main.py with
``--consumer payperuse_consumer``; the launcher only imports this module and
calls ``run()``.

The loop below is moved as-is from the old single-process root main.py — same
plain sync Consumer, same poll(), same batched-commit discipline. Every comment
here documents a failure that was actually hit; read them before changing the
offset handling.
"""
import asyncio
import functools
import signal
from concurrent.futures import ThreadPoolExecutor

from ai4i_core.bootstrap import init_database, close_database, init_redis
from ai4i_core.logging import get_logger
from confluent_kafka import Consumer, KafkaException, TopicPartition

from config import settings, build_consumer_config
from consumers.payperuse_consumer import handler  # noqa: F401 — side-effect import: populates TOPIC_REGISTRY
from consumers.registry import KafkaRegistry, TOPIC_REGISTRY

logger = get_logger(__name__)

# ===============
# DO NOT CHANGE: this is only 1 process that does lightweight io bound consumer tasks only,
# do not change, do not make it configurable, do not push it to settings.
#
# Still the legacy id: this group already has committed offsets for the topic,
# and KAFKA_AUTO_OFFSET_RESET is 'earliest', so renaming it would replay the
# whole topic from the beginning and re-bill every span in retention. Renaming
# it is an operational change (seed the new group's offsets first), not a code
# change.
GROUP_ID = "aio-python-consumers"
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


async def run() -> None:
    # ── Database ──
    db_cfg = settings.db_settings
    logger.info(
        "Initialising database | host=%s port=%d pool_size=%d max_overflow=%d"
        " platform_core_db=%s",
        db_cfg.POSTGRES_HOST,
        db_cfg.POSTGRES_PORT,
        db_cfg.DB_POOL_SIZE,
        db_cfg.DB_MAX_OVERFLOW,
        db_cfg.PLATFORM_CORE_DB,
    )
    try:
        await init_database(
            db_url=db_cfg.get_database_url(db_cfg.PLATFORM_CORE_DB),
            pool_size=db_cfg.DB_POOL_SIZE,
            max_overflow=db_cfg.DB_MAX_OVERFLOW,
        )
    except Exception as exc:
        logger.critical("Failed to initialise database | error=%s", exc)
        raise

    logger.info("Database ready | platform_core_db=%s", db_cfg.PLATFORM_CORE_DB)

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
    # One process per consumer, so this registry holds exactly this consumer's
    # handler: only consumers.payperuse_consumer.handler is imported above, and
    # @kafka_listener registers it under settings.topics.TOPIC_PAY_PER_USE.
    registry = KafkaRegistry(TOPIC_REGISTRY)
    logger.info(
        "Kafka registry ready | broker=%s group_id=%s topics=%s",
        settings.KAFKA_SERVER,
        GROUP_ID,
        registry.topics(),
    )

    # Plain sync Consumer, not confluent_kafka.aio.AIOConsumer: AIOConsumer
    # binds its background-thread -> event-loop callback bridge via the
    # deprecated asyncio.get_event_loop() (confluentinc/confluent-kafka-python
    # #2211, open/unfixed), which can silently attach to the wrong loop —
    # await consumer.poll() then hangs forever with no error, no exception,
    # no log line. The sync Consumer has no such bridge to get wrong: every
    # blocking call below is pushed onto _kafka_executor explicitly by us.
    consumer = Consumer(build_consumer_config(GROUP_ID, settings))
    # Single worker: our loop only ever has one poll()/commit() call in
    # flight at a time (each is awaited before the next is issued), and the
    # underlying librdkafka Consumer handle isn't safe to call concurrently
    # from multiple threads.
    _kafka_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kafka-consumer")

    try:
        consumer.subscribe(registry.topics())
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
        # asynchronous=False: block until the broker has acked the commit,
        # matching the previous AIOConsumer.commit()'s await semantics —
        # the default (asynchronous=True) would return immediately and
        # complete the round-trip in the background, which would let us
        # clear pending_offsets before the commit is actually durable.
        await loop.run_in_executor(
            _kafka_executor,
            functools.partial(consumer.commit, offsets=offsets, asynchronous=False),
        )
        pending_offsets = {}
        uncommitted = 0
        last_commit_time = loop.time()

    try:
        while not shutdown.is_set():
            try:
                msg = await loop.run_in_executor(
                    _kafka_executor, consumer.poll, settings.KAFKA_POLL_TIMEOUT_S
                )
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
    finally:
        # consumer.close() blocks briefly (leaves the group, one-off at
        # shutdown) — not worth routing through the executor.
        consumer.close()
        _kafka_executor.shutdown(wait=True)

    logger.info("Shutdown signal received — closing database connection")
    await close_database()
    logger.info("Consumer shut down cleanly.")
