import asyncio
import signal

from confluent_kafka import KafkaException
from confluent_kafka.aio import AIOConsumer

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

async def main() -> None:
    # ── Database registry ──
    db_cfg = settings.db_settings
    logger.info(
        "Initialising database registry | host=%s port=%d pool_size=%d max_overflow=%d"
        " inference_db=%s platform_core_db=%s",
        db_cfg.POSTGRES_HOST,
        db_cfg.POSTGRES_PORT,
        db_cfg.DB_POOL_SIZE,
        db_cfg.DB_MAX_OVERFLOW,
        db_cfg.INFERENCE_DB,
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

    async with consumer:
        while not shutdown.is_set():
            try:
                msg = await consumer.poll(timeout=settings.KAFKA_POLL_TIMEOUT_S)
            except KafkaException as exc:
                logger.error("Poll failed: %s", exc)
                continue

            if msg is None:
                continue
            if msg.error():
                logger.error("Kafka error: %s", msg.error())
                continue

            try:
                await registry.dispatch(msg.topic(), msg, consumer)
            except Exception as exc:
                logger.exception(
                    "Unhandled error dispatching message from topic %s: %s",
                    msg.topic(),
                    exc,
                )

    logger.info("Shutdown signal received — draining database connections")
    await db_registry.close_all()
    logger.info("Consumer shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
