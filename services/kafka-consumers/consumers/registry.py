from typing import Callable, Coroutine

from confluent_kafka.aio import AIOProducer
from ai4i_core.kafka import UltimatelyDLQException
from ai4i_core.logging import get_logger

logger = get_logger(__name__)

TOPIC_REGISTRY: dict[str, Callable] = {}


def kafka_listener(topic: str):
    def decorator(fn: Callable[..., Coroutine]):
        TOPIC_REGISTRY[topic] = fn
        return fn
    return decorator


class KafkaRegistry:
    """Orchestrator for Kafka topic consumption.

    Maintains a mapping of topic names to their registered async handler coroutines
    and routes each incoming message to the correct handler via :meth:`dispatch`.

    If a handler raises :exc:`UltimatelyDLQException`, the message is considered
    unrecoverable: the registry forwards it to the corresponding DLQ topic
    (``<topic>__dlq``) using the injected DLQ producer, then commits the offset so
    the message is never redelivered. Any other unhandled exception leaves the offset
    uncommitted, allowing the message to be reprocessed on restart.
    """

    def __init__(self, topic_registry: dict, dlq_producer: AIOProducer) -> None:
        self.handlers: dict[str, Callable] = topic_registry
        self._dlq_producer = dlq_producer

    def topics(self) -> list[str]:
        return list(self.handlers.keys())

    async def dispatch(self, topic: str, msg, consumer) -> None:
        try:
            await self.handlers[topic](msg)
            await consumer.commit(message=msg)
        except UltimatelyDLQException as exc:
            dlq_topic = f"{topic}__dlq"
            logger.error(
                "Sending message from topic %s to DLQ %s: %s",
                topic, dlq_topic, exc.message,
            )
            await self._dlq_producer.produce(
                topic=dlq_topic,
                value=msg.value(),
                key=msg.key(),
            )
            await consumer.commit(message=msg)
