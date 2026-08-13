# Kafka Consumers

> **This README describes the service as it actually is.**
> [ARCHITECTURE.md](./ARCHITECTURE.md) is a **target design** that is only
> partly built — it describes a `bootstrap/` package, `ManagedConsumer` and a
> consumer-group migration that do **not** exist yet. Where the two disagree,
> this file and the code are correct. Sections there are tagged `[SHIPPED]` /
> `[PLANNED]`.

One process per consumer. Each consumer package owns a `main.py` exposing
`async def run()` and hardcodes its own consumer group id. The service-root
`main.py` is the launcher: it takes `--consumer <name>`, validates it against
the `consumers/` directory, configures logging, imports `consumers.<name>.main`
and calls `run()`.

Each consumer's `run()` owns its own lifecycle (database, Redis, signal
handling), its consumer construction and its poll loop. There is no shared
runtime package yet — the launcher is self-contained in `main.py`, and shared
settings plus `build_consumer_config()` live in the service-root `config.py`.

The `@kafka_listener` topic registry (`consumers/registry.py`) is **still in
use**. What changed is its scope: each process imports exactly one consumer's
handler module, so `TOPIC_REGISTRY` holds only that consumer's topics.

Design intent, loop invariants, offset and error semantics, and the rules for
running multiple replicas are in [ARCHITECTURE.md](./ARCHITECTURE.md) — read its
status banner first.

```
services/kafka-consumers/
├── main.py                  # the launcher: argparse, validation, logging, importlib
├── config.py                # shared settings + Topics + Constants + build_consumer_config
└── consumers/
    ├── registry.py          # TOPIC_REGISTRY, kafka_listener, KafkaRegistry
    └── payperuse_consumer/  # one directory per consumer
        ├── main.py          #   GROUP_ID + run() + loop
        ├── handler.py       #   @kafka_listener(...) handle_ppu_usage
        └── _billing.py
```

## Available consumers

| `--consumer` | Consumer group | Topic | Purpose |
|---|---|---|---|
| `payperuse_consumer` | `aio-python-consumers` | `TOPIC_PAY_PER_USE` | Reads `ai-inference` OTel spans, deducts wallet balance, updates quota usage, and notifies `auth-service` when a tenant's budget or quota is exhausted |

> **The group id is unchanged, and no offset seeding is required to deploy this.**
> `payperuse_consumer` deliberately keeps the legacy `aio-python-consumers` id.
> That group already holds committed offsets for the topic and
> `KAFKA_AUTO_OFFSET_RESET` is `earliest`, so renaming it would replay the whole
> topic from the beginning and **re-bill every span still in retention**.
> Renaming is an operational change (seed the new group's offsets first), not a
> code change — see
> [ARCHITECTURE.md §10.2](./ARCHITECTURE.md#102-why-payperuse_consumer-keeps-the-legacy-group-id).

---

## Setup

### Prerequisites

- Python 3.11
- A running Kafka broker
- PostgreSQL: `PLATFORM_CORE_DB`
- Redis

### 1. Install dependencies

```bash
cd services/kafka-consumers
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp env.template .env
```

All settings currently live in the **service-root `config.py`** — `KafkaSettings`
(which nests `Topics`, `DatabaseSettings` and `RedisSettings`) plus the
`Constants` class. There is no per-consumer `config.py` yet, so every variable
below is read at import time by any consumer that runs. Splitting configuration
by ownership — so a consumer that does not talk to auth-service can boot without
`AUTH_SERVICE_URL` — is planned, not done.

**`config.py` (required by every consumer)**

| Variable | Default | Notes |
|---|---|---|
| `KAFKA_SERVER` | — | Bootstrap broker, `host:port`. Required. |
| `KAFKA_AUTO_OFFSET_RESET` | `earliest` | What happens when there is no valid committed offset. **This is a known risk on a billing consumer** — an offset that ages out of retention causes a silent full-topic replay and mass re-billing. Moving the default to `error` is planned and must be sequenced with the group-id migration; see [ARCHITECTURE.md §10](./ARCHITECTURE.md#10-offset-position-is-always-an-explicit-decision). |
| `KAFKA_ENABLE_AUTO_COMMIT` | `false` | Must stay false — the loop commits explicitly after a handler succeeds. |
| `KAFKA_SESSION_TIMEOUT_MS` | `30000` | Broker marks the consumer dead without a heartbeat in this window. |
| `KAFKA_MAX_POLL_INTERVAL_MS` | `300000` | Max gap between `poll()` calls before a rebalance. |
| `KAFKA_POLL_TIMEOUT_S` | `1.0` | Max blocking time per `poll()`. Also bounds shutdown latency. |
| `TOPIC_PAY_PER_USE` | — | Required. `kafka-topic-otel-trace` locally — the same topic inference-service exports spans to; the handler filters for `name == "ai-inference"`. |
| `AUTH_SERVICE_URL` | — | Required. Base URL of auth-service, used to push budget/quota-exhausted flags via `/internal/ppu/*`. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_HOST` | — | Required. |
| `POSTGRES_PORT` | `5432` | |
| `PLATFORM_CORE_DB` | — | Required. `ai4iplatform_core`. |
| `DB_POOL_SIZE` | `20` | |
| `DB_MAX_OVERFLOW` | `10` | |
| `REDIS_HOST` | — | Required. |
| `REDIS_PORT` | `6379` | |
| `REDIS_PASSWORD` | *(empty)* | |
| `REDIS_DB` | `0` | |
| `REDIS_TIMEOUT` | `10` | Socket timeout, passed to `init_redis(socket_timeout=...)`. |
| `REDIS_MAX_CONNECTIONS` | `50` | **Currently inert** — `ai4i_core.bootstrap.init_redis` exposes no pool-size knob. |

Cache prefixes and TTLs (`PPU_PRICING_CACHE_*`, `PPU_BILLED_KEY_*`) are
constants on `Constants` in `config.py`, not environment variables. The dedup key
TTL is deliberately 1 hour — see the comment on `Constants.PPU_BILLED_KEY_TTL`.

The commit cadence (`COMMIT_BATCH_SIZE = 100`, `COMMIT_INTERVAL_S = 5.0`) is a
module constant in `consumers/payperuse_consumer/main.py`, deliberately not a
setting. Read the comments there before changing the offset handling — each one
records a failure that was actually hit.

> `scripts/setup-env.sh` generates this service's `.env` from `env.template` by
> substituting values from the repo-root `.env`. Check `PLATFORM_CORE_DB` after
> running it: the root template leaves it empty and the service template's
> historical default (`platform_db`) does not match the `ai4iplatform_core`
> database used everywhere else.

### 3. Bring up local infrastructure (optional)

```bash
docker compose -f docker-compose-local.yml --profile streaming up -d kafka zookeeper
```

The broker is reachable at `localhost:9093` and runs
`infrastructure/kafka/local-init-kafka.sh` on startup, which creates a default
set of topics and consumer groups. Note that `kafka-topic-otel-trace` is **not**
among them — it is auto-created on first produce
(`KAFKA_AUTO_CREATE_TOPICS_ENABLE=true`) with broker-default partitioning.

Postgres and Redis come from the same compose file:

```bash
docker compose -f docker-compose-local.yml up -d postgres redis
```

---

## Running

### Locally

```bash
cd services/kafka-consumers
source .venv/bin/activate
python main.py --consumer payperuse_consumer
```

`--consumer` is required and has no environment fallback; omitting it is a
startup error, not a default. To see the valid names:

```bash
python main.py --list
```

An unknown or malformed name exits with code `2` and lists what is available.

On startup the process:

1. `main.py` parses and validates `--consumer` — regex **and** allow-list, before
   the name ever reaches `importlib.import_module()`
2. Configures logging as `kafka-consumer:<name>`. Nothing may configure logging
   before this line: `configure_logging()` clears root handlers
3. Imports `consumers/<name>/main.py`, logs its `GROUP_ID`, and calls `run()`
4. `run()` initialises the database and Redis via `ai4i_core.bootstrap`
   (`init_database`, `init_redis`)
5. Builds a plain `confluent_kafka.Consumer` from
   `build_consumer_config(GROUP_ID, settings)` and subscribes it to the topics in
   `TOPIC_REGISTRY` — which, in a one-consumer-per-process world, is just this
   consumer's
6. The loop begins polling one message at a time, dispatching via `KafkaRegistry`

The launcher deliberately **imports no config**. Pydantic settings read the
environment as they are constructed, so a launcher that imported one consumer's
config would let that consumer's missing variable break every other consumer's
process.

Stop with `Ctrl-C` (`SIGINT`) or `SIGTERM`. The loop exits, any pending offsets
are flushed with a final synchronous commit, the consumer leaves the group and
its executor drains, then the database engine is disposed. Shutdown takes up to
`KAFKA_POLL_TIMEOUT_S` because an in-flight blocking poll is not interrupted.

### In Docker

The build context is the **service folder**, not the repo root — the Dockerfile
does `COPY requirements.txt .` and `COPY . .` relative to it:

```bash
cd services/kafka-consumers
docker build -t kafka-consumers .
docker run --env-file .env kafka-consumers --consumer payperuse_consumer
```

The image has `ENTRYPOINT ["python", "main.py"]` and **no default `CMD`**, so
`--consumer` must be supplied by whatever runs the container. That is
intentional: a default would let a misconfigured deployment silently run the
wrong consumer.

One image, one container per consumer. **`replicas: 1` until the write-time guard
and the reconciliation job ship** — see
[ARCHITECTURE.md §8](./ARCHITECTURE.md#8-running-multiple-replicas--gated-on-the-write-time-guard).
Multiple replicas are the intended end state, but until the debit is guarded on
`(correlation_id, span_id)` in Postgres, a rebalance can leave two replicas
processing the same offsets and double-billing.

The image runs as non-root `appuser`. Its `HEALTHCHECK` greps `/proc/1/cmdline`
and confirms only that the process is alive — it does not verify broker,
database, or Redis connectivity, and it does not detect consumer lag.

---

## Adding a consumer

This is the procedure against the **current** tree. ARCHITECTURE.md §12 describes
a different one that assumes the unbuilt `bootstrap/` package — use this.

1. Create `consumers/<name>_consumer/` with an empty `__init__.py`.
2. Add the consumer's topic to `Topics` in the service-root `config.py`. There is
   no per-consumer `config.py` yet.
3. Add `handler.py` with an async function taking a `confluent_kafka.Message`,
   registered with `@kafka_listener(settings.topics.<TOPIC>)` from
   `consumers/registry.py`.
4. Add `main.py` with a hardcoded `GROUP_ID` and `async def run()`, importing the
   handler for its registration side effect:

   ```python
   from config import settings, build_consumer_config
   from consumers.<name>_consumer import handler  # noqa: F401 — populates TOPIC_REGISTRY
   from consumers.registry import KafkaRegistry, TOPIC_REGISTRY

   GROUP_ID = "..."          # read ARCHITECTURE.md §10 before choosing

   async def run() -> None:
       await init_database(...)
       await init_redis(...)
       registry = KafkaRegistry(TOPIC_REGISTRY)
       consumer = Consumer(build_consumer_config(GROUP_ID, settings))
       consumer.subscribe(registry.topics())
       ...   # loop: poll, dispatch, track offsets, commit
   ```

   Copy the loop body from `consumers/payperuse_consumer/main.py` — it is the
   reference implementation — and read its comments first; each documents a
   failure that was actually hit. Honour the invariants in
   [ARCHITECTURE.md §6](./ARCHITECTURE.md#6-loop-invariants) and
   [§7](./ARCHITECTURE.md#7-error-and-offset-semantics), noting the §6 banner on
   where the shipped loop knowingly differs. Nothing enforces them for you.
5. **Choose the group id deliberately.** With `KAFKA_AUTO_OFFSET_RESET=earliest`,
   a brand-new group replays the entire topic from the beginning. If that is not
   what you want, seed its offsets before first start —
   [ARCHITECTURE.md §10](./ARCHITECTURE.md#10-offset-position-is-always-an-explicit-decision).
6. Add a deployment unit passing `--consumer <name>_consumer`, `replicas: 1`.

No root `main.py` edit is needed — if `consumers/<name>/main.py` exists with a
callable `run`, the launcher can run it. If the copied loop ends up identical to
the reference implementation's, that is the signal to extract it into shared
code.

---

## Inspection

### Logs

Structured JSON on stdout via `ai4i_core.logging`, service name
`kafka-consumer-<name>`. Levels come from `LOG_LEVEL` / `ENVIRONMENT`.

Events worth watching:

| Line | Meaning |
|---|---|
| `Starting consumer \| name=... group_id=...` | From the launcher, before the consumer module runs. Confirms which consumer this process is |
| `Database ready \| platform_core_db=...` | Engine initialised |
| `Kafka registry ready \| broker=... group_id=... topics=...` | Handler registration resolved; confirms which group and topics this process owns |
| `Consumer started \| topics=... poll_timeout=... auto_offset_reset=...` | The loop is live |
| `Duplicate span detected — skipping billing` | Redelivery absorbed by the dedup key — expected after a restart |
| `Poll failed: ...` | A `KafkaException` from `poll()`. The loop logs and continues |
| `Unhandled error dispatching message from topic ...` | The handler raised. The offset is **not** recorded, so the message is redelivered on restart. There is no retry ladder and no partition rewind — alert on this |
| `Consumer shut down cleanly.` | Clean exit after SIGTERM/SIGINT |

Note that `trace_id` and `tenant_id` are null on every line — nothing in this
process populates the logging contextvars (`RequestMiddleware` is FastAPI-only).

### Kafka

Against the local broker (container `ai4v-kafka`, `localhost:9093`):

```bash
# List topics
docker exec ai4v-kafka kafka-topics --list --bootstrap-server localhost:9093

# Describe a topic (partitions, replication)
docker exec ai4v-kafka kafka-topics --describe --topic <topic> --bootstrap-server localhost:9093

# Tail a topic
docker exec ai4v-kafka kafka-console-consumer --bootstrap-server localhost:9093 \
    --topic <topic> --from-beginning

# Lag and offsets for one consumer — group ids are per-consumer now
docker exec ai4v-kafka kafka-consumer-groups --bootstrap-server localhost:9093 \
    --group <that-consumer's-group-id> --describe
```

The last command takes the group id of the consumer you are investigating (see
the table at the top). A non-zero `LAG` means messages are queued but not
processed — check that process's logs for retry or `CRITICAL` lines, and confirm
it still holds its group membership (`KAFKA_SESSION_TIMEOUT_MS` /
`KAFKA_MAX_POLL_INTERVAL_MS`).

**Do not run `--reset-offsets` against a live billing group.** Rewinding replays
spans, and anything older than the 1-hour dedup TTL is billed again.

---

## Testing

**There are none today.** This is the only one of the four backend services with
zero coverage, over a surface that includes the billing SQL and the dedup
semantics. Nothing in this service is currently verified by a test.

The planned layout puts tests **beside the code they cover**, in each package —
`consumers/<name>_consumer/tests/` for that consumer's handler and loop policy
(per-partition offset tracking, commit cadence, dispatch failure handling), plus
a shared-code suite once shared code exists. None of it needs a live broker,
database or Redis. See
[ARCHITECTURE.md §3.6](./ARCHITECTURE.md#36-bootstraptests) and
[§5](./ARCHITECTURE.md#5-the-consumer-contract) — both tagged `[PLANNED]`.

Until then, the launcher's behaviour can be smoke-checked without infrastructure:

```bash
cd services/kafka-consumers
source .venv/bin/activate

python main.py --list                       # enumerates consumers/
python main.py --consumer nope; echo $?     # exits 2, lists what is available
```

For what this design deliberately does *not* address, see
[ARCHITECTURE.md §11](./ARCHITECTURE.md#11-known-gaps).