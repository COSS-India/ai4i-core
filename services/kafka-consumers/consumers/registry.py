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

    Committing the offset is the caller's responsibility (see main.py's
    batched commit) — dispatch() only runs the handler, so a batch of
    messages can share one commit instead of one broker round-trip each.
    On failure, the exception propagates so the caller can log it and skip
    committing; the offset is left behind and the message is redelivered on
    restart (handlers must already be safe to reprocess for this reason —
    see the Redis dedup check in payperuse_consumer/handler.py).
    """

    def __init__(self, topic_registry: dict) -> None:
        self.handlers: dict[str, Callable] = topic_registry

    def topics(self) -> list[str]:
        return list(self.handlers.keys())

    async def dispatch(self, topic: str, msg) -> None:
        await self.handlers[topic](msg)
