import asyncio
import signal

from confluent_kafka import KafkaException
from confluent_kafka.aio import AIOConsumer

import consumers.payperuse_consumer  # noqa: F401 — side-effect import: populates TOPIC_REGISTRY
from ai4i_core.logging import get_logger
from config import settings, build_consumer_config
from consumers.registry import KafkaRegistry, TOPIC_REGISTRY

logger = get_logger(__name__)

# ===============
# DO NOT CHANGE: this is only 1 process that does lightweight io bound consumer tasks only,
# do not change, do not make it configurable, do not push it to settings
KAFKA_GROUP_ID = "aio-python-consumers"
# ===============

async def main() -> None:
    registry = KafkaRegistry(TOPIC_REGISTRY)

    consumer = AIOConsumer(build_consumer_config(KAFKA_GROUP_ID, settings))

    try:
        await consumer.subscribe(registry.topics())
    except KafkaException as exc:
        logger.critical("Failed to subscribe to Kafka topics: %s", exc)
        raise

    logger.info("Subscribed to topics: %s", registry.topics())

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

    logger.info("Consumer shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
