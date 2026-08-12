# Kafka Consumers

> **Status: TARGET DESIGN — NOT YET IMPLEMENTED.**
> This README describes the agreed redesign. The code currently on `release-2.4`
> still runs the old single-process flow (`python main.py` with no arguments,
> one consumer group for all topics). **The commands below will not work until
> the refactor lands.** See [ARCHITECTURE.md §1](./ARCHITECTURE.md#1-changes) for
> what changes and why.

One process per consumer. Each consumer package owns a `main.py` exposing
`async def run()` and hardcodes its own consumer group id. The service-root
`main.py` is a three-line entrypoint into `bootstrap.launcher`, which takes
`--consumer <name>`, imports `consumers.<name>.main`, and calls `run()`. There is
no topic registry.

Everything reusable lives in the service-local **`bootstrap/`** package: shared
settings, the launcher, process lifecycle (database, cache, signals), and
`ManagedConsumer` — a `confluent_kafka.Consumer` subclass that handles
construction, subscription and batch polling. Each consumer's `run()` supplies
its group id, topic and handler, and owns its own loop, error classification and
retry behaviour. Offset discipline — store and commit after every message, check
ownership before every message — is normative for all consumers, not a per-consumer
choice.

Full design — the bootstrap package, the consumer contract, loop invariants,
offset and error semantics, the rules for running multiple replicas, and the
group-id migration — is in [ARCHITECTURE.md](./ARCHITECTURE.md).

```
services/kafka-consumers/
├── main.py                  # → bootstrap.launcher.main()
├── bootstrap/               # reusable across consumers
│   ├── config.py            #   shared Kafka / Postgres / Redis settings
│   ├── launcher.py          #   argparse, validation, logging, module loading
│   ├── lifecycle.py         #   infra(), session_scope(), shutdown_event()
│   └── consumers.py         #   ManagedConsumer + build_bulk_message_consumer
└── consumers/
    └── payperuse_consumer/  # one directory per consumer
        ├── main.py          #   GROUP_ID + run() + loop
        ├── config.py        #   consumer-specific settings
        ├── handler.py
        └── _billing.py
```

## Available consumers

| `--consumer` | Consumer group | Topic | Purpose |
|---|---|---|---|
| `payperuse_consumer` | new, descriptive — **not** `aio-python-consumers` | `TOPIC_PAY_PER_USE` | Reads `ai-inference` OTel spans, deducts wallet balance, updates quota usage, and notifies `auth-service` when a tenant's budget or quota is exhausted |

> **The group id changes, and its offsets must be seeded before first start.**
> The legacy `aio-python-consumers` cannot be retained: the old process used the
> default eager assignor and this one uses `cooperative-sticky`, and a group
> cannot form when members share no common assignor. Because
> `KAFKA_AUTO_OFFSET_RESET` is `error`, an unseeded group **refuses to start**
> rather than replaying the topic. Read
> [ARCHITECTURE.md §10](./ARCHITECTURE.md#10-offset-position-is-always-an-explicit-decision)
> before deploying.

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

Configuration is split by ownership. Infrastructure every consumer needs lives in
`bootstrap/config.py`; anything specific to one consumer lives in that consumer's
own `config.py` and is only loaded when that consumer runs. A consumer that does
not talk to auth-service boots without `AUTH_SERVICE_URL` set.

**Shared — `bootstrap/config.py` (required by every consumer)**

| Variable | Default | Notes |
|---|---|---|
| `KAFKA_SERVER` | — | Bootstrap broker, `host:port`. Required. |
| `KAFKA_AUTO_OFFSET_RESET` | `error` | What happens when there is no valid committed offset. `error` surfaces it instead of silently replaying the topic; a new group must be seeded first. **Do not set `earliest` on a billing consumer** — see the note above. |
| `KAFKA_ENABLE_AUTO_COMMIT` | `false` | Must stay false — consumers commit explicitly after a handler succeeds. |
| `KAFKA_SESSION_TIMEOUT_MS` | `30000` | Broker marks the consumer dead without a heartbeat in this window. |
| `KAFKA_MAX_POLL_INTERVAL_MS` | `300000` | Max gap between fetches before a rebalance. Batch size × per-message time must stay well under it. |
| `KAFKA_POLL_TIMEOUT_S` | `1.0` | Max blocking time per fetch. Also bounds shutdown latency. |
| `KAFKA_BATCH_SIZE` | `1` | Messages requested per `consume()` call. **Do not raise without reading [ARCHITECTURE.md §6.4](./ARCHITECTURE.md#64-the-in-flight-window-and-the-revocation-fence)** — above 1 it opens an in-flight window during rebalances and re-enables a librdkafka batch-API hazard. Raising it requires the write-time guard and the reconciliation job to be in place. |
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

**`payperuse_consumer` — `consumers/payperuse_consumer/config.py`**

| Variable | Default | Notes |
|---|---|---|
| `TOPIC_PAY_PER_USE` | — | Required. `kafka-topic-otel-trace` locally — the same topic inference-service exports spans to; the handler filters for `name == "ai-inference"`. |
| `AUTH_SERVICE_URL` | — | Required. Base URL of auth-service, used to push budget/quota-exhausted flags via `/internal/ppu/*`. |

Cache prefixes and TTLs (`PPU_PRICING_CACHE_*`, `PPU_BILLED_KEY_*`) are constants
in the same module, not environment variables. The dedup key TTL is deliberately
1 hour — see the comment on `Constants.PPU_BILLED_KEY_TTL`.

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

1. `bootstrap.launcher` parses and validates `--consumer`
2. Configures logging as `kafka-consumer-<name>`
3. Imports `consumers/<name>/main.py` and calls `run()`
4. `run()` enters `infra()`, which initialises the database and Redis via
   `ai4i_core.bootstrap`
5. `ManagedConsumer.build_bulk_message_consumer(...)` constructs and subscribes
   one consumer, in that consumer's hardcoded group, to that consumer's topic
6. The consumer's own loop begins fetching batches

Stop with `Ctrl-C` (`SIGINT`) or `SIGTERM`. The loop exits, the consumer leaves
the group and its executor drains, then `infra()` disposes the database engine and
the Redis client. There is nothing to flush on the way out — every processed
message was committed as it went. Shutdown takes up to `KAFKA_POLL_TIMEOUT_S`
because an in-flight blocking fetch is not interrupted.

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

1. Create `consumers/<name>_consumer/` with an empty `__init__.py`.
2. Add `config.py` for that consumer's topic and service URLs. Do not put them in
   `bootstrap/config.py`.
3. Add the handler — a plain async function taking a `confluent_kafka.Message`.
   No decorator, no registration.
4. Add `main.py` with a hardcoded `GROUP_ID` and `async def run()`:

   ```python
   from bootstrap.consumers import ManagedConsumer
   from bootstrap.lifecycle import infra, shutdown_event

   GROUP_ID = "..."          # read ARCHITECTURE.md §10 before choosing

   async def run() -> None:
       async with infra(db_name=cfg.PLATFORM_CORE_DB):
           consumer = ManagedConsumer.build_bulk_message_consumer(
               group_id=GROUP_ID, topic=cfg.TOPIC,
           )
           shutdown = shutdown_event()
           try:
               while not shutdown.is_set():
                   batch = await consumer.consume_batch()
                   ...   # your loop: dispatch, offsets, commits, retries
           finally:
               consumer.shutdown()
   ```

   Copy the loop body from `consumers/payperuse_consumer/main.py` — it is the
   reference implementation — and honour the invariants in
   [ARCHITECTURE.md §6](./ARCHITECTURE.md#6-loop-invariants) and
   [§7](./ARCHITECTURE.md#7-error-and-offset-semantics). They are normative and
   not enforced by shared code.
5. **Seed the new group's offsets before first start** — with
   `KAFKA_AUTO_OFFSET_RESET=error`, a group that has never committed refuses to
   start. See
   [ARCHITECTURE.md §10](./ARCHITECTURE.md#10-offset-position-is-always-an-explicit-decision).
6. Add a deployment unit passing `--consumer <name>_consumer`, `replicas: 1`.

No root `main.py` edit, no registry. If the copied loop ends up identical to the
reference implementation's, promote it into `bootstrap/` and have both consumers
call it.

---

## Inspection

### Logs

Structured JSON on stdout via `ai4i_core.logging`, service name
`kafka-consumer-<name>`. Levels come from `LOG_LEVEL` / `ENVIRONMENT`.

Events worth watching:

| Line | Meaning |
|---|---|
| `Database ready \| ...` | Engine initialised |
| `Consumer started \| group_id=... topic=... batch_size=...` | The loop is live; confirms which group and topic this process owns |
| `Duplicate span detected — skipping billing` | Redelivery absorbed by the dedup key — expected after a restart |
| `Billing applied \| tenant=... cost=...` | A span was billed |
| `Handler failed — retrying` | Transient failure; the partition is rewound and retried |
| `CRITICAL` retry-exhausted line | A message was **dropped** after 3 attempts. Contains topic/partition/offset and the raw payload for manual replay. Alert on this. |

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

There are none today — this is the only one of the four backend services with
zero coverage, over a surface that includes the billing SQL and the dedup
semantics. The new layout fixes that by putting tests **beside the code they
cover**, in each package:

```bash
cd services/kafka-consumers
source .venv/bin/activate

pytest bootstrap/tests                        # shared code
pytest consumers/payperuse_consumer/tests     # one consumer
pytest                                        # everything
```

- **`bootstrap/tests/`** — launcher name validation and exit codes, settings and
  `build_consumer_config`, the named-connection registry and `session_scope`, and
  the `ManagedConsumer` factory. See
  [ARCHITECTURE.md §3.6](./ARCHITECTURE.md#36-bootstraptests).
- **`consumers/<name>_consumer/tests/`** — that consumer's handler, its config,
  and its loop policy: per-partition offset tracking, the retry ladder, and
  partial-batch abandonment. No shared code enforces those, so each consumer
  tests its own. A consumer is not complete without them. See
  [ARCHITECTURE.md §5](./ARCHITECTURE.md#5-the-consumer-contract).

None of it needs a live broker, database or Redis. Tests are excluded from the
runtime image by `.dockerignore` — they run from the repo, not the container.

For what this design deliberately does *not* address, see
[ARCHITECTURE.md §11](./ARCHITECTURE.md#11-known-gaps).