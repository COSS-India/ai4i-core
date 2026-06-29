from typing import Callable, Coroutine

TOPIC_REGISTRY: dict[str, Callable] = {}


def kafka_listener(topic: str):
    def decorator(fn: Callable[..., Coroutine]):
        TOPIC_REGISTRY[topic] = fn
        return fn
    return decorator


class ConsumerRegistry:
    def __init__(self):
        self.handlers: dict[str, Callable] = TOPIC_REGISTRY

    def topics(self) -> list[str]:
        return list(self.handlers.keys())

    async def dispatch(self, topic: str, msg) -> None:
        await self.handlers[topic](msg)
