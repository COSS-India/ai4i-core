# Kafka Consumers

A single async process that subscribes to multiple Kafka topics at once and routes each message to a handler registered for that topic via a `@kafka_listener` decorator. See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full design (startup sequence, registry internals, data flow, key decisions).

Currently registered consumers:

| Topic (env var) | Handler | Purpose |
|---|---|---|
| `TOPIC_PAY_PER_USE` | `consumers/payperuse_consumer/handler.py::handle_ppu_usage` | Reads `ai-inference` OTel spans, deducts wallet balance, updates quota usage, and notifies `auth-service` when a tenant's budget/quota is exhausted |

---

## Setup

### Prerequisites

- Python 3.11
- A running Kafka broker
- PostgreSQL database: `PLATFORM_CORE_DB`
- Redis

### 1. Install dependencies

```bash
cd services/kafka-consumers
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy the template and fill in values:

```bash
cp env.template .env
```

Key variables (see `env.template` for the full list and defaults):

- **Kafka** — `KAFKA_SERVER`, `KAFKA_AUTO_OFFSET_RESET`, `KAFKA_ENABLE_AUTO_COMMIT`, `KAFKA_SESSION_TIMEOUT_MS`, `KAFKA_MAX_POLL_INTERVAL_MS`, `KAFKA_POLL_TIMEOUT_S`
- **Topics** — `TOPIC_PAY_PER_USE`
- **Databases** — `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `PLATFORM_CORE_DB`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`
- **Redis** — `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`, `REDIS_TIMEOUT`, `REDIS_MAX_CONNECTIONS`
- **Internal service** — `AUTH_SERVICE_URL` (base URL of `auth-service`, used to push budget/quota-exhausted flags)

The consumer group ID (`aio-python-consumers`) is hardcoded in `main.py` and is **not** configurable — this process is designed to run as a single instance.

### 3. Bring up local infra (optional)

If you need a local broker/DB/Redis, the repo's root `docker-compose-local.yml` provides them under the `logging`/`streaming` profiles:

```bash
docker compose -f docker-compose-local.yml --profile streaming up -d kafka zookeeper
```

This runs `infrastructure/kafka/local-init-kafka.sh` on startup, which creates a default set of topics/consumer groups and is reachable at `localhost:9093`.

---

## Usage

### Run locally

```bash
cd services/kafka-consumers
source .venv/bin/activate
python main.py
```

On startup the process:
1. Initializes the `PLATFORM_CORE_DB` database engine
2. Connects to Redis
3. Subscribes a single Kafka consumer to every topic in `TOPIC_REGISTRY`
4. Enters the poll loop, dispatching each message by topic and committing the offset on success

Shut down with `Ctrl-C` (`SIGINT`) or `SIGTERM` — the process drains in-flight work and disposes DB connections before exiting.

### Run in Docker

```bash
# from the repo root, so the build context can reach libs/ if needed
docker build -f services/kafka-consumers/Dockerfile -t kafka-consumers .
docker run --env-file services/kafka-consumers/.env kafka-consumers
```

The image runs as a non-root `appuser` and has a `HEALTHCHECK` that verifies `main.py` is still the running process.

### Adding a new topic consumer

1. Create `consumers/<domain>_consumer/handler.py`.
2. Define `async def handle_<domain>(msg)` and decorate it with `@kafka_listener("your.topic.name")`.
3. Add a side-effect import in `main.py`: `import consumers.<domain>_consumer  # noqa: F401`.

No changes to `KafkaRegistry` or the poll loop are required — see [ARCHITECTURE.md § Adding a New Topic Consumer](./ARCHITECTURE.md#adding-a-new-topic-consumer).

---

## Inspection

### Logs

The service logs via `ai4i_core.logging` (structured, service name `aiokafka-consumer`). Key events to look for:

- `Database registry ready | count=... registered=[...]` — DB engines initialized
- `Kafka registry ready | broker=... group_id=... topics=[...]` — which topics this instance subscribed to
- `Consumer started | topics=... poll_timeout=...` — poll loop is live
- `Unhandled error dispatching message from topic %s` — a handler raised; offset was **not** committed, so the message will be redelivered on restart

### Inspecting Kafka directly

Against the local broker (container `ai4v-kafka`, `localhost:9093`):

```bash
# List all topics
docker exec ai4v-kafka kafka-topics --list --bootstrap-server localhost:9093

# Describe a topic (partitions, replication)
docker exec ai4v-kafka kafka-topics --describe --topic <topic-name> --bootstrap-server localhost:9093

# Tail messages on a topic
docker exec ai4v-kafka kafka-console-consumer --bootstrap-server localhost:9093 \
    --topic <topic-name> --from-beginning

# Check consumer group lag / offsets for this service
docker exec ai4v-kafka kafka-consumer-groups --bootstrap-server localhost:9093 \
    --group aio-python-consumers --describe
```

A non-zero `LAG` column in the last command means messages are queued but not yet processed — check the process logs for dispatch errors, or confirm the process is running and hasn't lost its group membership (`session.timeout.ms` / `max.poll.interval.ms` in `config.py`).

### Health check

The Docker image's `HEALTHCHECK` shells out to check that `main.py` is still `pid 1`'s process; it does not verify broker connectivity. For a stronger liveness signal, watch for periodic `Kafka error:` log lines or an absence of new "Message received" log lines when you expect traffic.