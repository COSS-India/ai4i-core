# Kafka Consumers

> **This README describes the service as it actually is.**
> [ARCHITECTURE.md](./ARCHITECTURE.md) is a design spec whose shared-code half is
> now built and whose consumer half is not: `bootstrap/` and `ManagedConsumer`
> exist, but `payperuse_consumer` has **not** been migrated onto them and still
> reads the superseded service-root `config.py`. Sections there are tagged
> `[SHIPPED]` / `[PLANNED]`. Where the two disagree, this file and the code are
> correct.
>
> **`bootstrap/config.py` regressed after this branch was first written.**
> `KAFKA_AUTO_OFFSET_RESET` shipped defaulting to `error` and `build_consumer_config()`
> shipped forcing `enable.auto.offset.store=False`; a later edit reverted the
> first to `earliest` and dropped the second entirely, without anyone updating
> this file or ARCHITECTURE.md at the time. Both are now wrong wherever they
> describe those two as fixed in `bootstrap/`. See "Configure environment" and
> [ARCHITECTURE.md §6.1](./ARCHITECTURE.md#61-fetch-in-bulk-commit-per-message)
> for what actually ships today and why it matters — in short,
> `ManagedConsumer`'s per-message-commit guarantee no longer holds, and no
> consumer gets `error`-on-unseeded-group protection by default.

One process per consumer. Each consumer package owns a `main.py` exposing
`async def run()` and hardcodes its own consumer group id. The service-root
`main.py` is a three-line delegation to `bootstrap.launcher.main()`, which takes
`--consumer <name>`, validates it against the `consumers/` directory, configures
logging, imports `consumers.<name>.main` and calls `run()`.

Reusable code lives in the service-local `bootstrap/` package: shared
infrastructure settings, the launcher, process lifecycle (database, Redis,
signals), and `ManagedConsumer` — a `confluent_kafka.Consumer` subclass that
owns construction, subscription, rebalance callbacks and async wrappers over
librdkafka's blocking calls. `bootstrap/` deliberately does **not** own the poll
loop; retry, error classification and drain behaviour stay with each consumer's
`run()`.

There is no topic registry. `consumers/registry.py` — `TOPIC_REGISTRY`,
`kafka_listener`, `KafkaRegistry` — is **deleted**. With one process per
consumer the subscription is a property of the consumer's own module: a
`TOPIC`/`topic=` declaration in its `main.py`, not a lookup table shared with
unrelated consumers. Handlers are plain async functions taking a
`confluent_kafka.Message`; there is no decorator and no registration
side-effect import.

Design intent, loop invariants, offset and error semantics, and the rules for
running multiple replicas are in [ARCHITECTURE.md](./ARCHITECTURE.md) — read its
status banner first.

```
services/kafka-consumers/
├── main.py                  # 3-line entrypoint → bootstrap.launcher.main()
├── config.py                # SUPERSEDED — infra settings + Topics + Constants +
│                            #   build_consumer_config; still read by payperuse_consumer
├── bootstrap/               # all reusable code
│   ├── __init__.py          #   lazy (PEP 562) re-exports of the public surface
│   ├── config.py            #   Kafka/Postgres/Redis settings + build_consumer_config
│   ├── launcher.py          #   argparse, validation, --list, logging, importlib
│   ├── lifecycle.py         #   infra(), add_database(), session_scope(), shutdown_event()
│   └── consumers.py         #   ManagedConsumer + build_bulk_message_consumer()
├── [PLANNED] tests/          # UNTRACKED prototype on disk (`git status`: `?? tests/`) —
│                            #   not part of this branch. See "Testing" below
│   ├── pytest.ini
│   ├── conftest.py
│   └── unit/bootstrap/      #   test_config, test_launcher, test_lifecycle, test_consumers
├── Dockerfile
├── .dockerignore            # present on disk but gitignored — see "In Docker"
├── env.template
├── requirements.txt         # runtime only; pytest is NOT in here — see "Testing"
├── README.md
├── ARCHITECTURE.md
└── consumers/
    ├── __init__.py          # EMPTY
    └── payperuse_consumer/  # one directory per consumer
        ├── __init__.py      #   EMPTY — no side-effect import
        ├── main.py          #   GROUP_ID + TOPIC + run() + loop
        ├── handler.py       #   handle_ppu_usage(msg) — plain async function
        └── _billing.py
```

## Available consumers

| `--consumer` | Consumer group | Topic | Purpose |
|---|---|---|---|
| `payperuse_consumer` | `aio-python-consumers` | `TOPIC_PAY_PER_USE` | Reads `ai-inference` OTel spans, deducts wallet balance, updates quota usage, and notifies `auth-service` when a tenant's budget or quota is exhausted |

> **The group id is unchanged, and no offset seeding is required to deploy this.**
> `payperuse_consumer` deliberately keeps the legacy `aio-python-consumers` id.
> That group already holds committed offsets for the topic, and the consumer
> reads `KAFKA_AUTO_OFFSET_RESET` from the service-root `config.py`, where it
> still defaults to `earliest` — so renaming the group would replay the whole
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

**Two settings modules read this `.env`, and they disagree on purpose.** Be sure
which one you are looking at:

- **`bootstrap/config.py`** — `KafkaSettings`, `DatabaseSettings`,
  `RedisSettings`, read lazily through `@lru_cache` accessors
  (`get_kafka_settings()` etc.), plus `build_consumer_config()`. Infrastructure
  only: no topics, no `AUTH_SERVICE_URL`, so a consumer that never calls
  auth-service can boot without it. This is what new consumers use.
- **`config.py` at the service root** — the superseded module, instantiated at
  import time as `settings`, nesting `Topics`, `DatabaseSettings` and
  `RedisSettings` plus the `Constants` class. It still exists because
  `payperuse_consumer` has not been migrated off it. Do not import it from new
  code.

**Only one librdkafka key still comes out different.** Two others used to, until
a later edit to `bootstrap/config.py` quietly eliminated both:

| Key | Root `config.py` | `bootstrap/config.py` |
|---|---|---|
| `auto.offset.reset` | `earliest` (from the setting's default) | `earliest` — **also the default now.** It shipped as `error` — the intended value, see [§10](./ARCHITECTURE.md#10-offset-position-is-always-an-explicit-decision) — for one revision of this branch, then was reverted. Nothing currently gives you the `error` protection unless you set it explicitly. |
| `enable.auto.offset.store` | not set → librdkafka default `true` | **also not set now** → same librdkafka default `true`. The `False` override was removed from `build_consumer_config()`. See [ARCHITECTURE.md §6.1](./ARCHITECTURE.md#61-fetch-in-bulk-commit-per-message) for why that key mattered — without it, `ManagedConsumer`'s per-message-commit guarantee does not hold. |
| `partition.assignment.strategy` | not set → default `range,roundrobin` | `cooperative-sticky` |

`bootstrap/config.py` additionally installs an `error_cb` and passes a `logger=`
for librdkafka's own output, neither of which the root module does. Note that
`enable.auto.commit` is **not** a divergence — both set it `False`, the root by
passing the setting through, `bootstrap/` by hardcoding it and rejecting `true`
with a validator.

A local, untracked prototype still asserts the old three-key table and the old
`error` default — 4 cases in `test_config.py` plus one in `test_consumers.py`
now fail against the current code, 5 total (see "Testing" below — no suite is
committed, so nothing enforces any of this today).

Because `payperuse_consumer` reads the root module, **the values below are what
that consumer actually gets today.** The `bootstrap/` column is what a new
consumer gets.

| Variable | Root `config.py` | `bootstrap/config.py` | Notes |
|---|---|---|---|
| `KAFKA_SERVER` | — (required) | — (required) | Bootstrap broker, `host:port`. |
| `KAFKA_AUTO_OFFSET_RESET` | `earliest` | `earliest` | What happens when there is no valid committed offset. `earliest` **is a known risk on a billing consumer** — an offset that ages out of retention causes a silent full-topic replay and mass re-billing. **`bootstrap/` no longer defaults to `error`** — it did for one revision of this branch, then was reverted to match the root default. Migrating `payperuse_consumer` to `bootstrap/config.py` does not fix this exposure by itself; only an explicit `KAFKA_AUTO_OFFSET_RESET=error` in that consumer's environment does, and on an *existing* group that must be sequenced with the group-id migration, see [ARCHITECTURE.md §10](./ARCHITECTURE.md#10-offset-position-is-always-an-explicit-decision). |
| `KAFKA_ENABLE_AUTO_COMMIT` | `false` | `false` | Must stay false — consumers commit explicitly after a handler succeeds. `bootstrap/config.py` rejects `true` with a validator; the root module would silently honour it. |
| `KAFKA_SESSION_TIMEOUT_MS` | `30000` | `30000` | Broker marks the consumer dead without a heartbeat in this window. |
| `KAFKA_MAX_POLL_INTERVAL_MS` | `300000` | `300000` | Max gap between fetches before the group evicts us. |
| `KAFKA_POLL_TIMEOUT_S` | `1.0` | `1.0` | Max blocking time per fetch. Also bounds shutdown latency. |
| `KAFKA_BATCH_SIZE` | *(not read)* | `1` | Messages per `consume()` call. **Leave at 1** — above 1 it opens an in-flight window during rebalances and re-enables librdkafka's batch-API hazard; see [ARCHITECTURE.md §6.4](./ARCHITECTURE.md#64-the-in-flight-window-and-the-revocation-fence) and [§11](./ARCHITECTURE.md#11-known-gaps). |
| `TOPIC_PAY_PER_USE` | — (required) | *(not read)* | `kafka-topic-otel-trace` locally — the same topic inference-service exports spans to; the handler filters for `name == "ai-inference"`. Topics are per-consumer and never live in `bootstrap/config.py`. |
| `AUTH_SERVICE_URL` | — (required) | *(not read)* | Base URL of auth-service, used to push budget/quota-exhausted flags via `/internal/ppu/*`. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_HOST` | — (required) | — (required) | |
| `POSTGRES_PORT` | `5432` | `5432` | |
| `PLATFORM_CORE_DB` | — (required) | — (required) | `ai4iplatform_core`. |
| `DB_POOL_SIZE` | `20` | `20` | |
| `DB_MAX_OVERFLOW` | `10` | `10` | |
| `REDIS_HOST` | — (required) | — (required) | |
| `REDIS_PORT` | `6379` | `6379` | |
| `REDIS_PASSWORD` | *(empty)* | *(empty)* | |
| `REDIS_DB` | `0` | `0` | |
| `REDIS_TIMEOUT` | `10` | `10` | Socket timeout. Passed to `init_redis(socket_timeout=...)` by `bootstrap.lifecycle.infra()`; **inert for `payperuse_consumer`**, which does not pass it. |
| `REDIS_MAX_CONNECTIONS` | `50` | `50` | **Currently inert in both** — `ai4i_core.bootstrap.init_redis` exposes no pool-size knob. |

Cache prefixes and TTLs (`PRICING_CACHE_*`, `BILLED_KEY_*`) are
constants on `Constants` in the root `config.py`, not environment variables. The
dedup key TTL is deliberately 1 hour — see the comment on
`Constants.BILLED_KEY_TTL`.

The commit cadence (`COMMIT_BATCH_SIZE = 100`, `COMMIT_INTERVAL_S = 5.0`) is a
module constant in `consumers/payperuse_consumer/main.py`, deliberately not a
setting. Read the comments there before changing the offset handling — each one
records a failure that was actually hit.

> **`scripts/setup-env.sh` does not actually configure this service.** It works
> by `sed`-substituting `<PLACEHOLDER>` tokens in each `env.template` from the
> repo-root `.env`, and this service's `env.template` contains **zero** such
> tokens — every value is a literal. The generated `.env` is therefore a verbatim
> copy, and nothing from the root `.env` reaches it. In particular you get
> `PLATFORM_CORE_DB=platform_db`, which does not match the `ai4iplatform_core`
> database used everywhere else. **Edit this service's `.env` by hand after
> running the script**, or add the placeholder tokens to `env.template`.

### 3. Bring up local infrastructure (optional)

`docker-compose-local.yml` lives at the **repo root**, not in this service — run
these from there, not from the directory step 1 left you in:

```bash
cd ../..    # repo root
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

1. `main.py` calls `bootstrap.launcher.main()`, which parses and validates
   `--consumer` — regex **and** allow-list, before the name ever reaches
   `importlib.import_module()`
2. Configures logging as `kafka-consumer-<name>`. Nothing may configure logging
   before this line: `configure_logging()` clears root handlers
3. Imports `consumers/<name>/main.py`, logs its `GROUP_ID`, and calls `run()`
4. `run()` initialises the database and Redis. For `payperuse_consumer` that is
   still `ai4i_core.bootstrap` directly (`init_database`, `init_redis`,
   `close_database`); a migrated consumer uses `bootstrap.lifecycle.infra()`
5. Builds its consumer and subscribes it to the topic declared in its own
   module. `payperuse_consumer` builds a plain `confluent_kafka.Consumer` from
   the root `config.py`'s `build_consumer_config(GROUP_ID, settings)` and
   subscribes to the module-level `TOPIC`; a migrated consumer calls
   `ManagedConsumer.build_bulk_message_consumer(group_id=..., topic=...)`,
   which subscribes and wires the rebalance callbacks for it
6. The loop begins polling and calls its handler directly — `handle_ppu_usage`
   for `payperuse_consumer`. There is no dispatch table

The launcher deliberately **imports no config** — neither `bootstrap.config` nor
a consumer's. Pydantic settings read the environment as they are constructed, so
a launcher that imported one consumer's config would let that consumer's missing
variable break every other consumer's process. `bootstrap/__init__.py`
re-exports lazily via PEP 562 for the same reason: `import bootstrap.launcher`
must not pull in `bootstrap.config`.

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

`.dockerignore` keeps `.env`, `.venv` and generated caches out of the image.
`tests/` is not on its exclude list — but `tests/` is also not a committed part
of this repo (see "Testing" below), so a fresh clone has nothing under that name
for `COPY . .` to pick up. The only way test code ends up in a locally built
image today is a checkout that still has the untracked prototype sitting in the
working tree, which is an accident of the builder's machine, not a documented
behaviour. If a real suite is committed later and the intent becomes "run it
against the built image", note that this would not work as the Dockerfile stands
regardless — it installs only `requirements.txt`, which has no `pytest` and no
`pytest-asyncio`.

Note also that `.dockerignore` is matched by the repo-root `.gitignore`
(line 75), so it is present on disk but **not tracked** — a fresh clone builds
without it and would bake in whatever `.env` the builder happens to have.
Recreate it before building.

---

## Adding a consumer

`bootstrap/` exists, so this is the procedure — the same one as
[ARCHITECTURE.md §12](./ARCHITECTURE.md#12-adding-a-new-consumer-shipped). Note that
`payperuse_consumer` does **not** follow it: it predates `bootstrap/` and is not
the shape to copy wholesale. Copy its loop *comments* and its offset discipline,
not its imports.

1. Create `consumers/<name>_consumer/` with an **empty** `__init__.py`. No
   side-effect import — nothing needs registering.
2. Add `consumers/<name>_consumer/config.py` for that consumer's topic, service
   URLs and domain constants. Nothing consumer-specific goes into
   `bootstrap/config.py`.
3. Add `handler.py` with a plain async function taking a
   `confluent_kafka.Message`. No decorator.
4. Add `main.py` with a hardcoded `GROUP_ID` and `async def run()`:

   ```python
   from bootstrap.consumers import ManagedConsumer
   from bootstrap.lifecycle import infra, shutdown_event
   from consumers.<name>_consumer import config as cfg
   from consumers.<name>_consumer.handler import handle_message

   GROUP_ID = "..."          # read ARCHITECTURE.md §10 before choosing

   async def run() -> None:
       async with infra(db_name=cfg.settings.PLATFORM_CORE_DB):
           consumer = ManagedConsumer.build_bulk_message_consumer(
               group_id=GROUP_ID,
               topic=cfg.settings.TOPIC_<NAME>,
           )
           shutdown = shutdown_event()
           try:
               while not shutdown.is_set():
                   for msg in await consumer.consume_batch():
                       if not consumer.owns(msg):
                           continue          # revoked mid-batch — §6.4 fence
                       ...                   # classify, handle, retry
                       await consumer.store_processed(msg)
                       await consumer.commit_stored()
           finally:
               consumer.shutdown()
   ```

   Honour the invariants in
   [ARCHITECTURE.md §6](./ARCHITECTURE.md#6-loop-invariants) and
   [§7](./ARCHITECTURE.md#7-error-and-offset-semantics) — the loop is the one
   thing `bootstrap/` does not enforce for you, and §6 carries a banner on where
   the shipped `payperuse_consumer` loop knowingly differs.
5. **Choose the group id deliberately, and set `KAFKA_AUTO_OFFSET_RESET=error`
   for this consumer yourself.** `bootstrap/config.py` does **not** default to
   `error` — it defaults to `earliest`, same as the root `config.py` — so
   nothing stops a brand-new group from silently replaying the whole topic
   unless you override the variable. Set it, then seed its offsets before first
   start ([ARCHITECTURE.md §10](./ARCHITECTURE.md#10-offset-position-is-always-an-explicit-decision)).
   Give the new consumer its own environment for this variable — it's a single
   process-level setting, so if the deployment's shared `.env` sets it to
   `earliest` for `payperuse_consumer`'s sake, a new consumer sharing that file
   inherits `earliest` too and replays the entire topic.
6. Add tests at `tests/unit/consumers/<name>_consumer/` covering the handler, the
   config, and the loop policy you wrote (§5). The loop is the part no shared
   code enforces — test it here or nothing does. **Note that `tests/` is not
   itself a committed part of this repo** (see "Testing" below) — landing it is
   a prerequisite, not something you can assume is already there.
7. Add a deployment unit passing `--consumer <name>_consumer`, `replicas: 1`.

No root `main.py` edit is needed and there is no registry to update — if
`consumers/<name>/main.py` exists with a callable `run`, the launcher can run it.

---

## Inspection

### Logs

Structured JSON on stdout via `ai4i_core.logging`, service name
`kafka-consumer-<name>`. Levels come from `LOG_LEVEL` / `ENVIRONMENT`.

From the launcher (`bootstrap/launcher.py`), every consumer:

| Line | Meaning |
|---|---|
| `Starting consumer \| name=... group_id=...` | Before the consumer module's `run()`. Confirms which consumer this process is |
| `Consumer exited cleanly \| name=...` | The launcher's last line, after `run()` returned |

From `payperuse_consumer`:

| Line | Meaning |
|---|---|
| `Database ready \| platform_core_db=...` | Engine initialised |
| `Kafka consumer configured \| broker=... group_id=... topic=...` | Confirms which group and topic this process owns |
| `Consumer started \| topic=... poll_timeout=... auto_offset_reset=...` | The loop is live |
| `Billing applied \| tenant=... service=... billed_units=... cost=... exhausted=...` | A span was priced and debited. The main success signal |
| `Duplicate span detected — skipping billing` | Redelivery absorbed by the dedup key — expected after a restart |
| `Redis dedup check failed — proceeding without dedup` | **Misleading — it does not proceed.** On any Redis error the dedup check returns `None` and the span is dropped without being billed, then its offset is committed. Alert on this: spans are silently lost while Redis is down. See [ARCHITECTURE.md §7.3](./ARCHITECTURE.md#73-infrastructure-failure-is-not-a-skip) |
| `Poll failed: ...` | A `KafkaException` from `poll()`. The loop logs and continues |
| `Unhandled error handling message from topic ...` | The handler raised. **Do not read this as "the message will be retried" — it will not.** The failed offset is not recorded, but `pending_offsets` is a per-partition high-water mark, so the next *successful* message on that partition commits past the failed one and it is never redelivered. There is no retry ladder and no rewind. This is a known defect, not a design choice — see [ARCHITECTURE.md §7.1](./ARCHITECTURE.md#71-a-failed-message-must-actually-be-retried). Alert on this line; the span is lost |
| `Consumer shut down cleanly.` | Clean exit after SIGTERM/SIGINT |

From `bootstrap/`, for a consumer built on it:

| Line | Meaning |
|---|---|
| `Consumer built \| group_id=... topic=... batch_size=... assignor=cooperative-sticky` | `ManagedConsumer` constructed and subscribed |
| `Partitions assigned \| added=... held=... generation=...` | Incremental assignment; normal on start and on every rebalance |
| `Partitions revoked \| revoked=... held=...` | Clean cooperative revoke |
| `Partitions LOST (no clean revoke) \| lost=...` | `session.timeout.ms` or `max.poll.interval.ms` exceeded. Another consumer may already be ahead of us on these partitions — work was very likely processed twice. **Alert on this** |
| `Broker error \| code=... fatal=...` | From librdkafka's `error_cb`, rate-limited to one line per error code per 60s. `_TRANSPORT` / `_ALL_BROKERS_DOWN` mean the consumer is disconnected while the healthcheck still sees a live process |
| `Commit rejected — assignment lost mid-message` | The partition moved while a message was in flight; the new owner will redo it |
| `Infrastructure closed` | `infra()` disposed the database and Redis on the way out |

Note that **trace context is absent but not obviously so.** Nothing in this
process populates the logging contextvars (`RequestMiddleware` is FastAPI-only),
and `ai4i_core.logging`'s formatter fills the gap rather than leaving it empty: it
generates a *fresh* `trace_id` per record and falls back to the literal string
`"system"` for `tenant_id`. So every line carries a plausible-looking trace id
that correlates with nothing, and no line is ever null. Do not try to group
consumer lines by `trace_id`. Setting it per message from the span's
`correlation_id` would make these logs correlate with inference logs — see
[ARCHITECTURE.md §11](./ARCHITECTURE.md#11-known-gaps).

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

## Testing **`[PLANNED]`** — nothing is committed

**There is no test suite for this service today.** `tests/` is not tracked —
`git status` reports `?? tests/` — so it is not part of this branch and is not
guaranteed to exist in a fresh clone. Do not run `pip install -r
requirements.txt` and expect a suite to be there; there is nothing to invoke.

What follows describes a **local, untracked prototype** that happens to be
sitting on disk, covering `bootstrap/` only. It is recorded here as a target
layout worth landing, not as shipped coverage — treat every number below as
"what the prototype currently does," not "what this service guarantees."

If you have that prototype checked out, its layout puts every test asset for
this service under `tests/` — test code, `conftest.py` and `pytest.ini` — which
makes `tests/` the pytest rootdir, so it would be invoked with a path:

**`requirements.txt` is runtime-only.** There is no `requirements-dev.txt` in
the tree, so `pytest` and `pytest-asyncio` are not installed by anything
committed — `pytest-asyncio` is not optional, since `tests/pytest.ini` sets
`asyncio_mode = auto`, without which every async test errors on an unknown
marker. Landing a real suite means deciding where these get declared.

```bash
cd services/kafka-consumers
source .venv/bin/activate
pip install pytest pytest-asyncio          # not declared anywhere yet

python -m pytest tests/unit                # 75 cases in the local prototype
cd tests && python -m pytest               # equivalent
```

A bare `pytest` from the service root finds no config, gets no `asyncio_mode`
and no `testpaths`, and would try to collect `.venv`.

**What the prototype currently covers** is the shared code only —
`tests/unit/bootstrap/` — as a starting point for whoever commits it:

| File | Under test |
|---|---|
| `test_launcher.py` | Name validation accepts valid names and rejects dotted paths and traversal; unknown names exit `2`; `--list` enumerates `consumers/`; a module without a callable `run` is rejected; the launcher imports no config |
| `test_config.py` | Settings parse from the environment and are read lazily (importing the module reads nothing); `KAFKA_BATCH_SIZE` defaults to `1`; asking for auto-commit fails loudly; the group id is not a setting; `build_consumer_config` takes `group_id` as a parameter and maps settings onto librdkafka keys; `BrokerErrorReporter` rate-limits per error code, not globally. **Stale as of the latest `bootstrap/config.py` edit — 4 of 28 cases now fail:** it still asserts `KAFKA_AUTO_OFFSET_RESET` defaults to `error`, that `enable.auto.offset.store` is a fixed correctness key, and that the root-config divergence is exactly three keys. All three are false against the code as it stands today |
| `test_lifecycle.py` | `add_database` is idempotent and rejects both-or-neither of `db_name`/`url`; `get_engine_for` raises when unopened and says what is open; `close_all_databases` disposes everything; `session_scope` rolls back **and re-raises** on error and leaves committing to the caller; `shutdown_event()` is set by both `SIGTERM` and `SIGINT` |
| `test_consumers.py` | `ManagedConsumer` can be constructed on top of the C extension type; the async wrappers have not shadowed an inherited method name; `build_bulk_message_consumer` applies settings defaults and subscribes to the given topic. **One case fails now** — `test_applies_settings_defaults` asserts `auto_offset_reset == "error"`, which is `"earliest"` against the current `bootstrap/config.py` (same root cause as `test_config.py` above) |

None of it needs a live broker, database or Redis. `conftest.py` supplies the
environment these settings modules require at import time, with the *intent*
that every endpoint be unreachable so a code path attempting real I/O fails
loudly rather than quietly succeeding against whatever is running locally. Note
that the intent is only partly realised: `KAFKA_SERVER=localhost:1` and
`AUTH_SERVICE_URL=http://auth.invalid` are genuinely unreachable, but
`POSTGRES_HOST` and `REDIS_HOST` are `localhost` on the default ports — i.e. the
same endpoints `docker-compose-local.yml` exposes. No current test opens a
connection, so this has not bitten yet; a new test that does would silently hit
the developer's real Postgres or Redis. Worth fixing before this is committed.

**`consumers/payperuse_consumer/` has no coverage in the prototype either** —
the billing SQL, the dedup semantics, the pricing resolution, the auth-service
notification and the loop's per-partition offset tracking are all unasserted,
including the two live defects called out in the logs table above (dropped
failed messages, dropped-on-Redis-error spans). A loop-policy test would have
caught both. Those tests would belong at
`tests/unit/consumers/payperuse_consumer/` and are the larger of the two gaps
once a shared-code suite is no longer the only thing missing.

For what this design deliberately does *not* address, see
[ARCHITECTURE.md §11](./ARCHITECTURE.md#11-known-gaps).
