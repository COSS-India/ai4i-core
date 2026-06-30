from typing import Callable, Coroutine

from ai4i_core.logging import get_logger

logger = get_logger(__name__)

TOPIC_REGISTRY: dict[str, Callable] = {}


def kafka_listener(topic: str):
    def decorator(fn: Callable[..., Coroutine]):
        TOPIC_REGISTRY[topic] = fn
        return fn
    return decorator


class KafkaRegistry:
    """Routes each incoming Kafka message to its registered async handler.

    On success, the offset is committed. On failure, the exception propagates
    so the caller can log it; the offset is left uncommitted and the message
    will be redelivered on restart.
    """

    def __init__(self, topic_registry: dict) -> None:
        self.handlers: dict[str, Callable] = topic_registry

    def topics(self) -> list[str]:
        return list(self.handlers.keys())

    async def dispatch(self, topic: str, msg, consumer) -> None:
        await self.handlers[topic](msg)
        await consumer.commit(message=msg)
