# Kafka Consumers — Architecture

## Overview

`services/kafka-consumers` is a single async process that listens on **multiple Kafka topics simultaneously**. Instead of spawning one process per topic, a single `aiokafka` consumer is subscribed to all registered topics and acts as an internal router — dispatching each incoming message to the handler that was registered for that topic.

Topic handlers are discovered automatically at startup through a **decorator-based registration** pattern, keeping `main.py` free of explicit handler lists.

---

## Startup Sequence

```
1. main.py starts
2. Import all consumer packages (triggers module-level decorator execution)
3. Decorators populate the global TOPIC_REGISTRY map: { topic_name → async handler fn }
4. ConsumerRegistry is instantiated, wrapping TOPIC_REGISTRY
5. aiokafka AIOKafkaConsumer subscribes to all keys of TOPIC_REGISTRY
6. Poll loop starts — each message is routed by topic to its registered handler
```

---

## Components

### `services/kafka-consumers/consumers/registry.py`

The single source of truth for both the decorator and the registry. It owns:

- **`TOPIC_REGISTRY`** — module-level global dict `{ topic_name → coroutine }`
- **`@kafka_topic`** — decorator that writes into `TOPIC_REGISTRY` at import time
- **`ConsumerRegistry`** — class that wraps `TOPIC_REGISTRY` and exposes it to `main.py`

`registry.py` is a pure leaf module — it imports nothing from `main.py` or any consumer package, so both `main.py` and consumer packages can safely import from it without creating a cycle.

```python
TOPIC_REGISTRY: dict[str, Coroutine] = {}

def kafka_topic(topic: str):
    def decorator(fn: Coroutine):
        TOPIC_REGISTRY[topic] = fn
        return fn
    return decorator

class ConsumerRegistry:
    def __init__(self):
        self.handlers: dict[str, Coroutine] = TOPIC_REGISTRY

    def topics(self) -> list[str]:
        return list(self.handlers.keys())

    async def dispatch(self, topic: str, msg, consumer) -> None:
        try:
            await self.handlers[topic](msg)
            await consumer.commit(message=msg)
        except UltimatelyDLQException as exc:
            # handler has declared the message unrecoverable; forward to DLQ
            await producer.produce(topic=f"{topic}__dlq", value=msg.value(), key=msg.key())
            await consumer.commit(message=msg)
        # any other exception: offset not committed → message is redelivered on restart
```

### `services/kafka-consumers/consumers/<name>/`

Each subdirectory is a consumer package for a logical domain (e.g. `payperuse_consumer`). It contains:

- `__init__.py` — re-exports the handler(s)
- `handler.py` — coroutines decorated with `@kafka_topic`, imported from `consumers.registry`

```python
# consumers/payperuse_consumer/handler.py
from consumers.registry import kafka_listener


@kafka_listener("ppu.usage.recorded")
async def handle_ppu_usage(msg) -> None:
    payload = json.loads(msg.value)
    ...
```

Adding a new topic means adding a new package here. `main.py` does **not** need to be changed.

### `services/kafka-consumers/main.py`

The process entrypoint. Responsibilities:

1. Import every consumer package so decorators execute and `TOPIC_REGISTRY` is populated.
2. Instantiate `ConsumerRegistry`.
3. Create a single `AIOKafkaConsumer` subscribed to `registry.topics()`.
4. Run the async poll loop, calling `registry.dispatch(msg.topic, msg)` for each message.
5. Handle graceful shutdown on `SIGTERM` / `SIGINT`.

```python
# Abbreviated shape
import consumers.payperuse_consumer  # noqa: F401 — side-effect import

async def main():
    registry = ConsumerRegistry()
    consumer = AIOKafkaConsumer(
        *registry.topics(),
        bootstrap_servers=settings.KAFKA_SERVER,
        group_id=settings.KAFKA_GROUP_ID,
        ...
    )
    async with consumer:
        async for msg in consumer:
            await registry.dispatch(msg.topic, msg)
```

---

## Data Flow

```
Kafka Broker
    │
    │  (all subscribed topics on one connection)
    ▼
AIOKafkaConsumer  (single consumer, single group_id)
    │
    │  msg.topic → TOPIC_REGISTRY lookup
    ▼
ConsumerRegistry.dispatch()
    │
    ├── "ppu.usage.recorded"  →  handle_ppu_usage(msg)  ──► success → commit offset
    │                                                     └► UltimatelyDLQException
    │                                                              │
    │                                                              ▼
    │                                                    produce to "ppu.usage.recorded__dlq"
    │                                                              │
    │                                                              ▼
    │                                                          commit offset
    ├── "other.topic"         →  handle_other(msg)
    └── ...

DLQ topic naming convention: <original_topic>__dlq
```

---

## Adding a New Topic Consumer

1. Create `services/kafka-consumers/consumers/<domain>_consumer/handler.py`.
2. Define an `async def handle_<domain>(msg)` and decorate it with `@kafka_topic("your.topic.name")`.
3. Add a side-effect import in `main.py`: `import consumers.<domain>_consumer`.

No changes to `ConsumerRegistry` or the poll loop are needed.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Single `aiokafka` consumer for all topics | Lower resource footprint; avoids one process/thread per topic |
| Decorator registration at import time | Zero-config discovery — adding a handler file is enough |
| Explicit side-effect imports in `main.py` | Makes the set of active consumers visible and auditable without scanning the filesystem |
| `ConsumerRegistry` wraps the global map | Keeps `main.py` decoupled from the global; easier to test by injecting a mock registry |
| `aiokafka` over confluent-kafka | All handlers are I/O-bound (DB writes, HTTP calls); async avoids blocking the poll loop |
| DLQ topic pattern `<topic>__dlq` | Double underscore avoids collisions with dot-separated topic hierarchies; derived at runtime so no DLQ topic config is needed per handler |
| `UltimatelyDLQException` signals DLQ routing | Keeps DLQ logic out of handlers — a handler raises the exception, `dispatch` owns the produce + commit |

---

## Relationship to `libs/ai4i_core/kafka`

`libs/ai4i_core/ai4i_core/kafka/base.py` provides `BaseKafkaConsumer`, a **sync, single-topic** base class backed by confluent-kafka. That abstraction is suitable for standalone consumers that own their own process.

This service takes a different approach: **async, multi-topic, decorator-routed**. The shared lib contributes:

- `KafkaSettings` / `build_consumer_config` — reused for connection config
- `UltimatelyDLQException` (`libs/ai4i_core/ai4i_core/kafka/exceptions.py`) — raised by any handler to signal that a message is unrecoverable and must be forwarded to its DLQ topic

The `@kafka_topic` decorator and `TOPIC_REGISTRY` global live in `consumers/registry.py` within this service, not in the shared lib.
