# Kafka Consumers Collection

## About

Standalone Kafka consumer processes for the ai4i-core platform. Each consumer runs as an
independent OS process (and container) that belongs to a single Kafka consumer group.

---

## Directory layout

```
services/consumers/
├── ARCHITECTURE.md          # this file
├── Dockerfile.template      # parameterised image definition (file_name variable)
├── deploy.sh                # builds & runs one consumer by name
├── env.template             # environment variable reference
├── requirements.txt         # pinned Python dependencies
└── services/
    ├── config.py            # shared Kafka / env config for all consumers
    ├── __init__.py
    └── <name>_consumer.py   # one file per consumer process
```

---

## Consumer file convention

| Rule | Detail |
|------|--------|
| **Naming** | Every consumer is a Python file whose name ends with `_consumer` (e.g. `ppu_usage_consumer.py`). |
| **One file = one process** | Each file owns exactly one `consumer group id`. Do not share a group id across files. |
| **Entry point** | The file must be runnable as `python services/<name>_consumer.py`. |
| **Location** | All consumer files live under `services/consumers/services/`. |

Existing consumers:

| File | Topic(s) | Group ID | Purpose |
|------|----------|----------|---------|
| `ppu_usage_consumer.py` | `usage` | TBD | Processes per-processing-unit usage events |

---

## Shared Kafka library

`libs/ai4i_core/ai4i_core/kafka/`

Centralised Kafka connection and configuration helpers shared by **all** consumers (and
producers elsewhere in the platform). Import from here instead of constructing
`confluent_kafka` objects directly inside a consumer file.

Responsibilities of this package:
- Build a `confluent_kafka.Consumer` / `Producer` from environment variables.
- Provide typed configuration dataclasses (bootstrap servers, security, group id, etc.).
- Expose thin helpers for common patterns (poll loop, commit strategy, dead-letter
  forwarding).

---

## Deployment

### `Dockerfile.template`

A parameterised Dockerfile that accepts the `file_name` build argument and runs the
corresponding consumer as its entrypoint:

```dockerfile
ARG file_name
# ...
ENTRYPOINT ["python", "services/${file_name}.py"]
```

The build context root is the **repository root** so that the shared `libs/` package can
be `COPY`-ed in alongside the consumer code.

### `deploy.sh`

Accepts a `--file_name` keyword argument, substitutes it into `Dockerfile.template`, and
builds + runs the resulting image:

```bash
# deploy a single consumer
./deploy.sh --file_name ppu_usage_consumer
```

Under the hood it runs roughly:

```bash
docker build \
  --build-arg file_name="${file_name}" \
  -f Dockerfile.template \
  -t "ai4i-consumer-${file_name}" \
  .
docker run --env-file .env "ai4i-consumer-${file_name}"
```

---

## Configuration

Consumers read their settings from environment variables (see `env.template`).
Kafka-specific variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_ENABLED` | `false` | Set `true` to activate Kafka connections |
| `KAFKA_SERVER` | `localhost:9093` | Bootstrap broker address |
| `KAFKA_TOPIC_OTEL_TRACE` | `kafka-topic-otel-trace` | OTel trace topic (producer side) |

Consumer-specific group ids and topic names are defined in each `_consumer.py` file (or
pulled from additional env vars declared there).

---

## Adding a new consumer

1. Create `services/consumers/services/<name>_consumer.py`.
2. Use the Kafka helpers from `libs/ai4i_core/ai4i_core/kafka/` for connection setup.
3. Set a unique `group.id` for the consumer group.
4. Deploy with `./deploy.sh --file_name <name>_consumer`.