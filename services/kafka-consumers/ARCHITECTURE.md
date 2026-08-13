# kafka-consumers — Architecture Changes

> ## ⚠️ Status: target design, only partly built
>
> **This document describes where the service is going, not what it does today.**
> Read it as a design spec. Where a section describes something not yet in the
> repo it is tagged **`[PLANNED]`**; sections tagged **`[SHIPPED]`** match the
> code on this branch. When in doubt, the code wins.
>
> **What is shipped today:**
>
> - One process per consumer, selected by `--consumer <name>` (§4).
> - The root `main.py` launcher: argparse, name validation, `--list`, logging
>   setup, `importlib` + `asyncio.run(run())` — implemented *directly in that
>   file*, not delegated to a `bootstrap/` package.
> - `consumers/payperuse_consumer/main.py` owning its `GROUP_ID`, lifecycle and
>   poll loop, moved as-is from the old monolithic root `main.py`.
>
> **What is NOT built yet** — every mention of these below is aspirational:
>
> | Described in this doc | Reality on this branch |
> |---|---|
> | `bootstrap/` package (`config.py`, `launcher.py`, `lifecycle.py`, `consumers.py`, `tests/`) | Does not exist. No such package is tracked in the repo. |
> | `ManagedConsumer`, `build_bulk_message_consumer()`, `infra()`, `session_scope()`, `shutdown_event()` | Do not exist. The loop uses a plain `confluent_kafka.Consumer` built by `build_consumer_config()` in the service-root `config.py`. |
> | `consumers/registry.py` removed | Still present, and actively imported by `consumers/payperuse_consumer/main.py` and `handler.py`. |
> | A new, descriptive consumer group id | `GROUP_ID = "aio-python-consumers"` — the legacy id, deliberately retained (§10.2). |
> | `KAFKA_AUTO_OFFSET_RESET` defaults to `error` | Defaults to `earliest` (`config.py`). |
> | `partition.assignment.strategy = cooperative-sticky`, rebalance callbacks, the revocation fence, batch fetch | Not configured and not implemented. The shipped loop is a single-message `poll()`. |
> | Per-message commit (§6.1), `store_offsets()`/`commit()`, no `pending_offsets` dict | **The shipped loop does the opposite** — it batches commits every 100 messages or 5 seconds via an explicit `pending_offsets` dict. See the §6 note. |
>
> Sections §6–§9 describe invariants for the **target** loop. The shipped loop
> satisfies §6.2 (an offset is committed only after its handler succeeds) and
> §6.6–§6.7, and **knowingly departs from §6.1/§6.8**.

---

## 1. Changes

### The old flow (removed on this branch)

One process, one consumer group (`aio-python-consumers`, hardcoded in the root
`main.py`), one `confluent_kafka.Consumer` subscribed to **every** topic in a
module-global `TOPIC_REGISTRY`, with the poll loop living in the root `main.py`
itself. Handlers register themselves with a `@kafka_listener("topic")` decorator
(`consumers/registry.py`) and are wired in by a side-effect import. A
`KafkaRegistry` routes each polled message to the handler registered for its
topic.

### The flow today **`[SHIPPED]`**

**One process per consumer.** Each consumer package owns a `main.py` exposing
`async def run()` and hardcodes its own consumer group id. The service-root
`main.py` is a thin launcher: it takes `--consumer <name>` from deployment,
validates the name against the `consumers/` directory, configures logging,
imports `consumers.<name>.main`, and calls `run()`.

The registry **still exists and is still used**. `consumers/registry.py`
(`TOPIC_REGISTRY`, `kafka_listener`, `KafkaRegistry`) is unchanged; what changed
is its scope. Because each process imports exactly one consumer's handler
module, `TOPIC_REGISTRY` now holds exactly that consumer's topics — the
process-wide, all-topics fan-in is gone even though the mechanism is not.

```
                    deployment
                        │  --consumer payperuse_consumer
                        ▼
        ┌────────────────────────────────────────────┐
        │  main.py                                   │
        │    argparse → validate name → --list       │
        │    configure_logging()                     │
        │    importlib → asyncio.run(run())          │
        └───────────────────┬────────────────────────┘
                            ▼
        ┌────────────────────────────────────────────┐
        │  consumers/payperuse_consumer/main.py      │
        │    GROUP_ID = "aio-python-consumers"       │
        │    run():                                  │
        │      init_database() / init_redis()        │
        │      registry = KafkaRegistry(...)         │
        │      consumer = Consumer(                  │
        │          build_consumer_config(GROUP_ID))  │
        │      while not shutdown:                   │
        │        msg = await poll()                  │
        │        dispatch → batched commit           │
        └───────────────────┬────────────────────────┘
                            ▼
        consumers/payperuse_consumer/handler.py  →  _billing.py
```

### The target flow **`[PLANNED]`**

**A service-local `bootstrap/` package holds everything reusable** — the
launcher methods, shared settings, process lifecycle (database, cache,
signals), and a `confluent_kafka.Consumer` subclass that encapsulates
construction and polling. Any abstraction shared by more than one consumer
belongs there and nowhere else.

At that point the topic registry concept is **removed entirely** —
`consumers/registry.py` (`TOPIC_REGISTRY`, `kafka_listener`, `KafkaRegistry`)
is deleted and topics are declared by the consumer that consumes them. **None of
this has been built yet.**

```
                    deployment
                        │  --consumer payperuse_consumer
                        ▼
        ┌────────────────────────────────────────────┐
        │  main.py                                   │
        │    → bootstrap.launcher.main()             │
        │        argparse → validate → logging       │
        │        → importlib → asyncio.run(run())    │
        └───────────────────┬────────────────────────┘
                            ▼
        ┌────────────────────────────────────────────┐   uses
        │  consumers/payperuse_consumer/main.py      │ ──────────┐
        │    GROUP_ID = "..."                        │           │
        │    run():                                  │           ▼
        │      async with infra(...):                │   ┌──────────────────┐
        │        consumer = ManagedConsumer          │   │  bootstrap/      │
        │            .build_bulk_message_consumer()  │   │   config.py      │
        │        while not shutdown:                 │   │   launcher.py    │
        │          batch = await consume_batch()     │   │   lifecycle.py   │
        │          ... handle / commit / retry ...   │   │   consumers.py   │
        └───────────────────┬────────────────────────┘   └──────────────────┘
                            ▼
        consumers/payperuse_consumer/handler.py  →  _billing.py
```

---

## 2. Target file layout **`[PLANNED]`**

> This is the destination, **not** the current tree. Today there is no
> `bootstrap/` package, no `tests/` directories, no per-consumer `config.py`,
> and `consumers/registry.py` is still present and in use. The current tree is:
>
> ```
> services/kafka-consumers/
> ├── main.py                       # the launcher itself (~105 lines), §4
> ├── config.py                     # shared settings + build_consumer_config
> ├── Dockerfile
> ├── env.template
> ├── README.md
> ├── ARCHITECTURE.md               # this file
> └── consumers/
>     ├── __init__.py
>     ├── registry.py               # STILL PRESENT — TOPIC_REGISTRY, kafka_listener, KafkaRegistry
>     └── payperuse_consumer/
>         ├── __init__.py
>         ├── main.py               # GROUP_ID + run() + loop
>         ├── handler.py            # @kafka_listener("...") handle_ppu_usage
>         └── _billing.py
> ```

```
services/kafka-consumers/
├── main.py                       # 3-line entrypoint → bootstrap.launcher.main()
├── bootstrap/                    # ALL reusable code lives here
│   ├── __init__.py               # public surface re-exports
│   ├── config.py                 # shared settings (Kafka / Postgres / Redis) + build_consumer_config
│   ├── launcher.py               # argparse, name validation, --list, logging, importlib, asyncio.run
│   ├── lifecycle.py              # infra() ctx manager (DB + Redis), session_scope(), shutdown_event()
│   ├── consumers.py              # ManagedConsumer(confluent_kafka.Consumer) + factories
│   └── tests/                    # unit tests for the shared code — §3.6
├── Dockerfile                    # ENTRYPOINT unchanged; no default CMD
├── .dockerignore                 # keeps .env / .venv / tests out of the image — see §9
├── env.template
├── README.md
├── ARCHITECTURE.md               # this file
└── consumers/
    ├── __init__.py
    └── payperuse_consumer/
        ├── __init__.py           # EMPTY — no side-effect import
        ├── main.py               # GROUP_ID + run() + loop + fence + retries
        ├── config.py             # PPU-only settings + Constants
        ├── handler.py            # handle_ppu_usage(msg) — decorator removed
        ├── _billing.py           # unchanged
        └── tests/                # THIS consumer's unit tests — §5
```

**To be deleted:** `consumers/registry.py` (still present today).
**To be moved:** the service-root `config.py` becomes `bootstrap/config.py`.

---

## 3. The `bootstrap/` package **`[PLANNED]`**

> **None of §3 exists yet.** There is no `services/kafka-consumers/bootstrap/`
> package in the repo. Everything below — `ManagedConsumer`, `infra()`,
> `session_scope()`, `shutdown_event()`, `build_bulk_message_consumer()`, the
> launcher module, the shared-code tests — is a specification for work that has
> not been done. Do not import from it and do not cite it as current behaviour.
> Shared settings and `build_consumer_config()` currently live in the
> service-root `config.py`.

`bootstrap/` is the designated home for reusable code. A consumer package should
contain only what is genuinely specific to that consumer: its group id, its
topic, its settings, its handler, and its loop policy.

> **Naming note.** This package shadows nothing, but it is *not*
> `ai4i_core.bootstrap` — the shared PyPI library. It wraps it. When both are in
> scope, import the library one by its full path
> (`from ai4i_core.bootstrap import init_database`) and the local one relatively
> (`from bootstrap.consumers import ManagedConsumer`) so the distinction is
> visible at the import line.

### 3.1 `bootstrap/config.py`

Everything that is infrastructure rather than domain, moved wholesale from the
old service-root `config.py`:

- `KafkaSettings` — `KAFKA_SERVER`, `KAFKA_AUTO_OFFSET_RESET`,
  `KAFKA_ENABLE_AUTO_COMMIT`, `KAFKA_SESSION_TIMEOUT_MS`,
  `KAFKA_MAX_POLL_INTERVAL_MS`, `KAFKA_POLL_TIMEOUT_S`, and the new
  `KAFKA_BATCH_SIZE` (§3.4) — **default `1`**; see §6.4 for the two
  preconditions that must hold before raising it.
- `DatabaseSettings` — Postgres connection plus `get_database_url(db)`.
- `RedisSettings` — Redis connection plus `get_redis_url()`.
- `build_consumer_config(group_id, settings) -> dict` — translates settings into
  a librdkafka config dict. The group id is a **parameter**, never a setting.

Some keys are **fixed in `build_consumer_config`, not configurable** — they are
correctness, not tuning:

| Key | Value | Why |
|---|---|---|
| `enable.auto.commit` | `False` | §6.1 |
| `enable.auto.offset.store` | `False` | §6.1 |
| `partition.assignment.strategy` | `cooperative-sticky` | §6.5 |
| `error_cb` | a callback | Without one, `_TRANSPORT` / `_ALL_BROKERS_DOWN` never reach the application: the binding always registers a default that discards them. The consumer can then be disconnected indefinitely while `consume()` returns `[]`, the loop spins, and the Docker healthcheck sees a live process. **Log on state change only** — measured, it fires 42 times in 2 seconds while a broker is unreachable. |
| `logger=` (constructor kwarg, not config) | the service logger | Routes librdkafka's own output through `ai4i_core.logging`. Without it, `FAIL` lines go to raw stderr in librdkafka's `%3\|…\|FAIL\|` format — visible in `docker logs`, but not structured JSON and not parseable into OpenSearch. |

**`KAFKA_AUTO_OFFSET_RESET` should default to `error`, not `earliest`.** See
§10: with `earliest`, an offset that ages out of retention causes a silent
full-topic replay and mass double-billing. `error` turns that into an
`_AUTO_OFFSET_RESET` error entry — an alert and a human decision. The
consequence is deliberate: **a brand-new consumer group has no committed offsets
and will refuse to start until they are seeded** (§10). That is the safety
property, not a bug.

> **Not yet true.** `config.py` currently defaults `KAFKA_AUTO_OFFSET_RESET` to
> `earliest`, and `build_consumer_config()` sets only `bootstrap.servers`,
> `group.id`, `auto.offset.reset`, `enable.auto.commit`, `session.timeout.ms`
> and `max.poll.interval.ms`. `enable.auto.offset.store`,
> `partition.assignment.strategy`, `error_cb` and `logger=` are **not** set —
> the fixed-keys table above is a target, not a description of the shipped
> config. Changing the default to `error` is a breaking operational change for
> the existing `aio-python-consumers` group and must be sequenced with the
> seeding step in §10.2.

`Topics` and `AUTH_SERVICE_URL` do **not** live here — they are per-consumer
(§5). A consumer that does not talk to auth-service must be able to boot without
`AUTH_SERVICE_URL` set.

### 3.2 `bootstrap/launcher.py`

The whole launcher, so the root `main.py` is three lines. Responsibilities, in
order:

1. **Parse arguments.** `argparse` with a single `--consumer` argument,
   `required=True`. There is **no environment-variable fallback and no default**.
   A deployment that forgets the argument must fail loudly at startup rather than
   silently running the wrong consumer, and there must be exactly one mechanism
   so there is never a question of precedence. A `--list` flag prints the
   available consumers and exits.
2. **Validate the name.** It must match `^[a-z][a-z0-9_]*$` **and** name a
   directory under `consumers/` containing a `main.py`. Anything else exits `2`
   with a message listing the valid names.

   > This validation is a security control, not ergonomics. The value is fed to
   > `importlib.import_module()`. An unvalidated value (`../../something`, or any
   > dotted path) is arbitrary module import inside the container. The same
   > directory enumeration backs `--list` and the error message.

3. **Configure logging** — `configure_logging(service_name=f"kafka-consumer-{name}")`
   from `ai4i_core.logging`, called **before** importing the consumer module so
   import-time log records are formatted, and per-consumer so processes are
   distinguishable in OpenSearch. (This also retires the misleading
   `aiokafka-consumer` name the old code used.)
4. **Load and run** — `importlib.import_module(f"consumers.{name}.main")`, fetch
   `run`, verify it is callable, `asyncio.run(run())`.

**The launcher must not import any config** — neither `bootstrap.config` nor a
consumer's `config.py`. Pydantic settings instantiate at import time, so a
launcher that imported shared or foreign config would let consumer A's missing
environment variable break consumer B's process — precisely the coupling this
refactor removes. Config is imported by the consumer module, at step 4, after
the name is known.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Clean shutdown after SIGTERM/SIGINT |
| `2` | Unknown or malformed `--consumer`, or the module has no callable `run` |
| non-zero | Startup failure (DB, Redis, or broker) — the orchestrator restarts |

### 3.3 `bootstrap/lifecycle.py`

Process-lifetime concerns, so no consumer re-derives initialisation or teardown
order.

Every consumer gets **one database connection opened for it automatically, from
default settings**. Consumers that need more open them explicitly through the
named-connection methods below.

#### `infra(...)` — the default connection and the cache

An async context manager wrapping `ai4i_core.bootstrap`. On entry it calls
`init_database(...)` with the database name and `DatabaseSettings`' pool
defaults (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`) and `init_redis(...)`. On exit, in a
`finally`, it calls `close_database()`, **every named connection the consumer
opened**, and `close_redis()`.

```python
@asynccontextmanager
async def infra(
    *,
    db_name: str,
    pool_size: int | None = None,
    max_overflow: int | None = None,
) -> AsyncIterator[None]:
    """Open the default database + Redis; close them and every named
    connection on the way out."""
```

This is the only place `ai4i_core.bootstrap.init_database` is called.
**Never call it a second time** — it holds one module-global engine and
reassigns it without disposing the first, silently leaking the connection pool.
A second database goes through `add_database()`, not a second `init_database()`.

#### Named connections — additional databases

`ai4i_core.bootstrap` cannot hold two engines, so `bootstrap/lifecycle.py` keeps
its own registry for the extras. This mirrors what auth-service already does for
its secondary connection (`services/auth-service/app/core/database.py`:
`init_platform_core_database` / `close_platform_core_database` /
`get_platform_core_db`), generalised from one hardcoded secondary to a
name-keyed collection so a consumer can open as many as it needs.

```python
_engines: dict[str, AsyncEngine] = {}
_session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}


async def add_database(
    name: str,
    *,
    db_name: str | None = None,
    url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
) -> None:
    """Open a named connection. Idempotent — a no-op if `name` is already
    open, so a consumer may call it from more than one code path."""


def get_engine_for(name: str) -> AsyncEngine:
    """The named engine. Raises if it was never opened."""


async def close_database_connection(name: str) -> None:
    """Dispose one named engine. No-op if absent."""


async def close_all_databases() -> None:
    """Dispose every named engine. Called by infra() on the way out."""
```

| Method | Purpose |
|---|---|
| `add_database(name, ...)` | Open an additional connection under a caller-chosen key |
| `session_scope(name)` | A transactional session on that connection |
| `get_engine_for(name)` | The raw `AsyncEngine`, for `text()` execution outside a session |
| `close_database_connection(name)` | Dispose one |
| `close_all_databases()` | Dispose all — `infra()` calls this, so consumers normally do not |

Give `db_name` for another database on the **same** Postgres instance and the URL
is built from `DatabaseSettings.get_database_url(db_name)`, so credentials are
declared once. Give `url` instead for a **different** instance with its own
credentials — the same fallback shape as auth-service's
`get_platform_core_db_url()`, where per-database user/password/host/port fall
back to the shared `POSTGRES_*` values when unset. Pool sizes default to
`DatabaseSettings` when omitted.

Note the name: `close_database_connection`, not `close_database`. The latter is
already imported from `ai4i_core.bootstrap` and closes the *default* connection;
two functions one letter apart that close different things is exactly the kind of
collision the `ManagedConsumer` wrapper naming in §3.4 avoids.

#### `session_scope(name=None)`

An `@asynccontextmanager` yielding an `AsyncSession` that rolls back and re-raises
on error. With no argument it binds to the default connection's engine; with a
name it binds to that named connection's sessionmaker.

```python
@asynccontextmanager
async def session_scope(name: str | None = None) -> AsyncIterator[AsyncSession]:
    factory = _session_factories[name] if name else _default_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

The default factory is built once from `get_engine()` — `init_database` creates
the engine, `get_engine()` hands it over — so this still initialises through
`ai4i_core.bootstrap`. Committing remains the caller's job in both cases.

Do **not** wrap `ai4i_core.bootstrap.get_db()` instead. That function is shaped
as a FastAPI dependency (an async generator); wrapping it means an exception in
the `async with` body propagates out of the `async for` and leaves the generator
suspended, so its `except Exception: await session.rollback()` branch is
finalised later by the event loop's async-generator hooks rather than
deterministically at the error. The same applies to any named connection — expose
`session_scope`, never a `get_*_db()` generator.

#### `shutdown_event()`

Returns an `asyncio.Event` with `SIGTERM` and `SIGINT` wired to set it via
`loop.add_signal_handler`.

#### Cache

Use `ai4i_core.bootstrap.get_redis_client()` — the library documents it as the
accessor for non-DI contexts. `get_redis()` is the FastAPI dependency and must
not be used here. There is one Redis client per process; unlike databases, no
named-connection registry exists for it, and none should be added until a
consumer actually needs a second instance.

#### Usage

```python
async def run() -> None:
    # default connection opened from settings — nothing to declare
    async with infra(db_name=cfg.PLATFORM_CORE_DB):
        await add_database("auth", db_name=cfg.AUTH_DB)      # extra, optional

        async with session_scope() as db:                    # default
            ...
        async with session_scope("auth") as auth_db:         # named
            ...
    # infra() has closed the default connection, "auth", and Redis
```

### 3.4 `bootstrap/consumers.py`

A subclass of `confluent_kafka.Consumer` that carries its own identity and
provides async wrappers over the library's blocking calls.

```python
class ManagedConsumer(Consumer):
    """confluent_kafka.Consumer that knows its group, topic and poll settings,
    and exposes async wrappers over librdkafka's blocking calls."""

    def __init__(
        self,
        config: dict,
        *,
        group_id: str,
        topic: str,
        poll_timeout: float,
        batch_size: int,
        auto_offset_reset: str,
        thread_name_prefix: str,
    ) -> None:
        super().__init__(config)        # config is the ONLY thing the C type sees
        self.group_id = group_id
        self.topic = topic
        self.poll_timeout = poll_timeout
        self.batch_size = batch_size
        self.auto_offset_reset = auto_offset_reset
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=thread_name_prefix,
        )

    @classmethod
    def build_bulk_message_consumer(
        cls,
        *,
        group_id: str,
        topic: str,
        settings: KafkaSettings | None = None,
        batch_size: int | None = None,
        poll_timeout: float | None = None,
        thread_name_prefix: str | None = None,
    ) -> "ManagedConsumer":
        """Construct, configure and subscribe a batch-fetch consumer."""

    # ── Assignment state, for the §6.4 revocation fence. Written by the
    #    callbacks on the executor thread, read by the loop on the event
    #    loop; plain assignment is adequate under the GIL (§6.6).
    _assigned: set[tuple[str, int]]
    _generation: int

    def owns(self, msg: Message) -> bool:
        """True if this consumer still holds msg's partition. Synchronous —
        the loop calls it before every message."""

    # ── Rebalance callbacks — handed to subscribe(). librdkafka runs them on
    #    the executor thread from inside consume(): synchronous, short, no
    #    await, and NO commit (§6.5). They use incremental_assign /
    #    incremental_unassign because the protocol is COOPERATIVE.
    def on_assign(self, consumer, partitions: list[TopicPartition]) -> None: ...
    def on_revoke(self, consumer, partitions: list[TopicPartition]) -> None: ...
    def on_lost(self, consumer, partitions: list[TopicPartition]) -> None: ...

    # ── Async wrappers over the blocking calls — see §6.6
    async def consume_batch(self) -> list[Message]: ...
    async def store_processed(self, msg: Message) -> None: ...   # → store_offsets
    async def commit_stored(
        self, offsets: list[TopicPartition] | None = None,
    ) -> None: ...                       # → commit; swallows _NO_OFFSET
    def shutdown(self) -> None: ...      # close() + executor.shutdown(wait=True)
```

There is deliberately **no `seek_to`**. Retry works on the in-hand `Message`
object (§7.1), so nothing in this design ever moves the fetch position by hand —
which removes librdkafka's "avoid storing offsets after `seek()`" ordering hazard
along with it.

**`commit_stored` swallows `_NO_OFFSET` internally.** `commit()` raises
`KafkaException(_NO_OFFSET)` when nothing new has been stored — verified against
confluent-kafka 2.15.0 — which happens routinely on a redelivered message that
was already committed. Absorbing it in the shared wrapper means no consumer can
reintroduce that crash loop.

**`build_bulk_message_consumer`** produces a consumer built on the **batch-fetch
API** — `consume(num_messages=batch_size, timeout=poll_timeout)`, which returns a
*list* per call rather than one message per `poll()`.

`batch_size` **defaults to 1**. That is not a contradiction of the name: the
batch API is what the consumer is built on, and 1 is the safe setting for it
today. Above 1 the fetch saves executor round-trips when the consumer is behind,
at the cost of an in-flight window and a librdkafka rebalance hazard — §6.4 gives
the two preconditions for raising it. Keeping the batch API means that is a
config change, not a rewrite.

The factory defaults every unspecified argument from `KafkaSettings`, calls
`build_consumer_config(group_id, settings)`, constructs the instance, and calls
`subscribe([topic], on_assign=..., on_revoke=..., on_lost=...)` before returning
it — so a consumer's `run()` never subscribes by hand and cannot forget to wire
the rebalance callbacks (§6.5).

Three implementation caveats that belong in the code as comments:

- **`Consumer` is a C extension type** (`confluent_kafka.cimpl.Consumer`), and
  subclassing it **works** — verified against confluent-kafka 2.15.0:
  `super().__init__(config)`, then ordinary attribute assignment, then custom
  methods, with no `__new__` override needed. Pass the config dict as the sole
  argument to `super().__init__()` and set everything else afterwards; do not try
  to forward keyword arguments through to the base type.
- **Do not shadow inherited method names.** `poll`, `consume`, `commit`,
  `store_offsets`, `subscribe`, `assign`, `seek`, `pause`, `resume`, `position`,
  `committed` and `close` all come from the C type. That is why the wrappers are
  named `consume_batch`, `store_processed`, `commit_stored` and `shutdown` —
  each delegates to the inherited call of the obvious name.
  Overriding `commit` or `store_offsets` with an async method would break every
  internal caller expecting the synchronous one — including librdkafka's own
  internal use during close and rebalance, which runs on its thread, not the
  event loop.
- **One executor worker, never more.** The underlying librdkafka handle is not
  safe to call concurrently from multiple threads, and the loop only ever has one
  call in flight. `thread_name_prefix` exists so a thread dump names the consumer.

### 3.5 Where the line is drawn

`bootstrap/` owns **construction and polling**. It does **not** own the loop.

| Owned by `bootstrap/` | Owned by each consumer's `run()` |
|---|---|
| Settings, `build_consumer_config` | Its `GROUP_ID` and topic |
| Argument parsing, validation, logging, module loading | Which database it opens |
| DB/Redis init and teardown, session scope, signal wiring | The poll loop itself |
| `ManagedConsumer` construction, subscribe, executor | Calling store + commit after each message (§6.1) |
| Rebalance callbacks and the assignment state behind `owns()` (§6.4) | Checking `owns()` before every message |
| Async wrappers: `consume_batch`, `store_processed`, `commit_stored`, `shutdown` | Retry, backoff, and failure classification |
| | Drain-and-exit sequencing |

This is a deliberate line. Sharing construction removes copy-paste that has no
business varying; leaving the loop with the consumer lets each one choose its own
retry ladder, error classification and drain behaviour without negotiating with an
abstraction shared by the others.

What is *not* a per-consumer choice: the offset discipline in §6 — store and
commit after every message, check `owns()` before every message. Those are
normative for all consumers, and §6.8 explains why commit batching in particular
is not on the menu for anything with money side effects.

**The cost, stated plainly:** the offset and retry logic in §6 and §7 is *not*
enforced by shared code. It will be copied from
`consumers/payperuse_consumer/main.py`, which is therefore the **reference
implementation**, and the invariants below are **normative**. A copy that
violates them is a bug regardless of whether it appears to work. If a second
consumer ends up with a byte-identical loop, that is the signal to promote the
loop into `bootstrap/` — not a reason to have done so preemptively.

### 3.6 Tests for the shared code — now at `tests/unit/bootstrap/`

> **`[SUPERSEDED]` — this section's location and its status banner are both out of
> date. See [`tests/TESTPLAN.md`](./tests/TESTPLAN.md).**
>
> The old banner said *"no `bootstrap/tests/` directory exists … the service
> currently has no tracked test suite at all"*. That has been false for some time:
> the suite was written (**81 cases**), and has since moved. Every test asset for
> this service now lives under `services/kafka-consumers/tests/` — test code,
> `conftest.py`, `pytest.ini`, `requirements-dev.txt` and the test plan itself — so
> the shared code's tests are at `tests/unit/bootstrap/`, **not** beside the code.
> Run them with `python -m pytest tests/unit` (the path matters: `tests/` is the
> pytest rootdir).
>
> The table below still describes the right assertions; only "beside it" is wrong.

The shared code carries its own unit tests. Everything `bootstrap/`
exposes is testable without a broker, a database or Redis:

| Under test | What the tests assert |
|---|---|
| `launcher.py` | Name validation accepts valid names and rejects dotted paths and traversal; unknown names exit `2`; `--list` enumerates the `consumers/` directory; a module without a callable `run` is rejected |
| `config.py` | Settings parse from the environment; `build_consumer_config` maps them to the right librdkafka keys and takes `group_id` as a parameter |
| `lifecycle.py` | The named-connection registry: `add_database` is idempotent, `get_engine_for` raises when unopened, `close_all_databases` disposes everything, and `session_scope` rolls back and re-raises on error |
| `consumers.py` | `build_bulk_message_consumer` applies settings defaults, subscribes to the given topic, and produces an instance whose `group_id` / `topic` / `batch_size` are what was asked for |

The subclass caveats in §3.4 are worth a test each — that `ManagedConsumer` can
actually be constructed on top of the C extension type, and that the async
wrappers have not shadowed an inherited method name. Both fail loudly in a test
and silently in production.

---

## 4. The launcher (`main.py`) **`[SHIPPED]`**

The root `main.py` **is** the launcher — argparse, name validation, `--list`,
logging setup, `importlib` and `asyncio.run(run())` are all implemented directly
in that file (~105 lines). It owns the responsibilities listed in §3.2:

```python
CONSUMERS_DIR = Path(__file__).resolve().parent / "consumers"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

def available_consumers() -> list[str]:
    """Directories under consumers/ that hold a main.py and have a legal name."""
    ...

def main(argv: list[str] | None = None) -> None:
    # --consumer / --list, mutually exclusive and required
    # regex AND allow-list validation before importlib.import_module()
    # configure_logging(service_name=f"kafka-consumer:{name}")
    # asyncio.run(run())
    ...

if __name__ == "__main__":
    main()
```

Two invariants the file enforces and comments in place:

- **It imports no config.** Pydantic settings read the environment at
  construction, so a launcher that imported one consumer's config would let that
  consumer's missing variable break every other consumer's process. Config is
  imported by the consumer module, after its name is known.
- **`--consumer` is validated by regex *and* allow-list** before reaching
  `importlib.import_module()`. An unvalidated value (`"../../something"`, or any
  dotted path) is arbitrary module import inside the container. Neither check
  may be relaxed to accept dotted paths.

Exit codes: `0` on clean shutdown after SIGTERM/SIGINT; `2` for an unknown or
malformed `--consumer` or a module with no callable `run`; non-zero for a
startup failure (database, Redis, broker), which the orchestrator restarts.

> **`[PLANNED]`** — the target is to move this body into `bootstrap/launcher.py`
> so the root file reduces to a three-line delegation and the logic becomes
> testable without spawning a process:
>
> ```python
> from bootstrap.launcher import main
>
> if __name__ == "__main__":
>     main()
> ```
>
> That module does not exist yet.

---

## 5. The consumer contract

> **Partly shipped.** `GROUP_ID` and `async def run()` are real and enforced —
> the launcher exits `2` if `run` is missing or not callable, and logs
> `GROUP_ID` at startup. The rest is `[PLANNED]`: `run()` is currently assembled
> from `ai4i_core.bootstrap` (`init_database`, `init_redis`, `close_database`)
> and the service-root `config.py` directly, **not** from a local `bootstrap/`
> package; `payperuse_consumer` has no `config.py` and no `tests/` of its own.

Every `consumers/<name>/main.py` **must** expose:

- **`GROUP_ID: str`** — a hardcoded module constant. Never read from settings,
  never overridable by environment. See
  [§8](#8-running-multiple-replicas--gated-on-the-write-time-guard) for why, and
  [§10](#10-offset-position-is-always-an-explicit-decision) before you choose or
  change one.
- **`async def run() -> None`** — the lifecycle, assembled from `bootstrap/`.

Its own `config.py` holds anything specific to it — its topic, service URLs, and
domain constants. Nothing consumer-specific goes in `bootstrap/config.py`.

### Optional: `rollback` — the escape hatch, not the mechanism

A consumer **may** expose `async def rollback(msg) -> None`, called when a
side effect must be compensated because the message should not have been
processed. **`payperuse_consumer` does not implement it, and should not.**

Prefer making the write conditional (§8.2): the guard and the debit are the same
SQL statement, so the losing consumer never writes and there is nothing to undo.
That is strictly better than compensating, for three reasons:

- **Detection needs a durable record anyway.** Nothing tells consumer A that
  consumer B also processed a span — `on_revoke` carries no such information, and
  by the time it fires A has already committed. Any reliable duplicate check is a
  lookup on `(correlation_id, span_id)`, which is exactly what §8.2's guard
  already does at write time. Once you have that, rollback is redundant; without
  it, rollback has nothing to trigger on.
- **It moves the failure window instead of closing it.** Debit, then crash before
  compensating, and the compensation never runs.
- **The compensation is itself a racing write**, competing with the other
  consumer's debit and every other concurrent debit on that wallet.

`rollback` exists for the case the conditional write cannot cover: a consumer
whose non-idempotent side effects reach **outside the database** — a payment
gateway, an email send, a third-party API — where there is no shared transaction
to gate on. That is a Saga-style compensation, and it is appropriate only when
atomicity is genuinely unavailable. A consumer that implements `rollback` must
document in its module docstring which effect is being compensated and what
happens if the compensation itself fails.

### Its own tests

> **`[SUPERSEDED]` — the *location* rule below is reversed.** Tests no longer live
> inside the consumer package. Every test asset for this service is under
> `services/kafka-consumers/tests/`, so a consumer's unit tests belong at
> `tests/unit/consumers/<name>/`. See [`tests/TESTPLAN.md`](./tests/TESTPLAN.md) §4.0
> for the layout and §10 for the conformance suites that let a new consumer inherit
> the whole matrix by registering one row.
>
> **What a consumer must be covered for is unchanged** — the list below is still
> correct, and so is the reason for it. One refinement: the loop-policy invariants
> are *additionally* enforced centrally by a parameterized conformance suite
> (TESTPLAN §10.1), because a contract that gets copied can still be checked once.

~~**Every consumer package carries its unit tests inside it**, at
`consumers/<name>_consumer/tests/`.~~ A consumer without tests is not complete.
They cover:

- **The handler** — message parsing, the success / skip / failure classification
  of §7, and the domain logic behind it (for `payperuse_consumer`: dedup, pricing
  resolution, the billing write, and the auth-service notification).
- **Its config** — required variables are required, defaults are what the
  deployment expects.
- **Its loop policy** — the part §3.5 leaves to the consumer and no shared code
  enforces: the `owns()` fence being checked before every message (§6.4), the
  error classification of §6.3, the retry ladder (§7.1), and that store + commit
  happen after every message and only on success (§6.1, §6.2). These are exactly
  the invariants a copied loop can regress silently, which is why they are tested
  per consumer rather than once centrally.

None of this needs a live broker, database or Redis. Kafka messages are fakes
carrying `topic()` / `partition()` / `offset()` / `value()`; the database and
cache are mocked, the same way the other three services' conftests already do it.
Tests living beside the consumer is what lets one be added, tested and deployed
without touching anything shared.

### Shape of `run()`

```python
GROUP_ID = "ppu-billing-consumer"          # NOT the legacy id — see §10

async def run() -> None:
    async with infra(db_name=cfg.PLATFORM_CORE_DB):
        consumer = ManagedConsumer.build_bulk_message_consumer(
            group_id=GROUP_ID,
            topic=cfg.TOPIC_PAY_PER_USE,
        )
        shutdown = shutdown_event()
        try:
            while not shutdown.is_set():
                for msg in await consumer.consume_batch():   # bulk fetch
                    if not consumer.owns(msg):
                        continue          # revoked mid-batch — §6.4 fence
                    if not usable(msg):
                        continue          # error entry — §6.3 classification
                    await handle_with_retry(msg)             # in-hand — §7.1
                    await consumer.store_processed(msg)
                    await consumer.commit_stored()           # per message
        finally:
            consumer.shutdown()
```

Four things this shape encodes, each load-bearing:

- **Fetch in bulk, commit sequentially.** Nothing to flush at the end — every
  processed message was committed as it went (§6.1).
- **`owns()` before anything else.** A rebalance can revoke a partition while its
  messages are still in this batch; processing them would duplicate work the new
  owner is already doing (§6.4).
- **Classify before handling.** Only a fatal error entry may take the process
  down (§6.3).
- **Retry in hand, never seek.** The failed message is retried in place; leaving
  it uncommitted is what guarantees redelivery after a crash (§7.1).

`infra()` guarantees the database and Redis are closed; `consumer.shutdown()`
leaves the consumer group and drains the executor. The loop between them is the
consumer's own.

---

## 6. Loop invariants

Normative for every consumer.

> ### ⚠️ The shipped loop departs from §6.1 and §6.8
>
> `consumers/payperuse_consumer/main.py` **batches its commits**:
> `COMMIT_BATCH_SIZE = 100` messages or `COMMIT_INTERVAL_S = 5.0` seconds,
> whichever comes first, tracked in an explicit
> `pending_offsets: dict[(topic, partition), offset]` and flushed with
> `commit(offsets=..., asynchronous=False)`. §6.1 mandates a commit after **each**
> message and states there is no `pending_offsets` dict to maintain; §6.8
> explicitly withdraws the carve-out that would permit batching for a consumer
> with money side effects.
>
> **This is a known, deliberate divergence, not an oversight.** The loop was moved
> as-is from the old monolithic root `main.py` — this branch is a
> launcher/consumer split and changes no offset semantics. The in-code rationale
> is that `handle_ppu_usage` is redelivery-safe via the Redis dedup check, so a
> mid-batch crash redelivers up to 100 already-billed messages that then no-op.
> §6.8 rejects exactly that argument, on the grounds that the dedup key has a
> 1-hour TTL on an LRU instance and so is not a durable idempotency guarantee.
>
> **Unresolved.** Either the loop moves to per-message commit or §6.1/§6.8 are
> amended to permit the batched form with a stated bound; until one of those
> happens, treat §6.1's code sketch as target-state and the shipped comments in
> `payperuse_consumer/main.py` as the description of current behaviour. The
> shipped comments document failures that were actually hit (the 8-partition
> per-partition-offset bug in particular) and should be read before touching the
> offset handling.
>
> Note that §6.2 **is** satisfied: an offset only enters `pending_offsets` after
> its `dispatch()` returns successfully, and a failed message `continue`s without
> recording its offset.

### 6.1 Fetch in bulk, commit per message

**Bulk applies to the fetch, not to the commit.**

The failure that decides this: fetch 10 messages, process 5, crash before
committing. Those 5 are uncommitted, so on restart all 10 are redelivered and the
5 completed ones are processed a second time. For a billing consumer that means 5
spans re-billed — and the only thing standing in the way is a Redis key with a
1-hour TTL on an LRU instance (§8.2). Any commit window wider than one message
turns one crash into that many duplicate side effects.

This is a rule about **commit cadence, not batch size**. It would still matter if
the loop fetched one message at a time and committed every hundredth — which is
exactly the "optimisation" §6.8 rules out.

So: after **each** message's handler returns successfully, store its offset and
commit, before moving to the next message.

```
consume_batch()          → up to KAFKA_BATCH_SIZE messages, one broker round-trip
  for each message:
      handler(msg)       → the side effect (DB write, notification)
      store_processed()  → local, marks this offset committable
      commit_stored()    → synchronous broker round-trip
```

The crash window shrinks from "the whole batch" to "one message" — the gap
between a side effect landing and its commit landing. That gap cannot be closed:
Kafka alone gives exactly-once only against another Kafka topic, never against a
database or an HTTP call. Per-message commit makes it as small as it can be, and
the handler's own idempotency (§7.4) covers what remains.

**Be precise about what this does and does not cover.** Per-message commit solves
the *crash* case completely. It does **nothing** for the *ownership* case — a
rebalance mid-batch, where the messages were already handed to this process
before anything went wrong. That is a separate problem with a separate guard;
see §6.4.

**Two config keys make this possible**, both **false**:

| Key | Why false |
|---|---|
| `enable.auto.commit` | Nothing is committed on a timer behind your back. |
| `enable.auto.offset.store` | **The important one.** Left at its default (`true`), a fetch marks a message's offset committable the instant it is returned — *including* messages whose processing later raised. Any commit would then advance past a failed message. |

With both off, offset bookkeeping is a two-step the library already provides:

- **`store_offsets(msg)`** — record "this one is safe to commit". Local only, no
  broker round-trip.
- **`commit()`** — write the highest stored offset **for every assigned
  partition** to `__consumer_offsets`.

That is the whole mechanism. There is no `pending_offsets` dict to maintain:
`store_offsets` already tracks the high-water mark per partition, and already
stores `msg.offset() + 1`, so the manual `+1` that explicit `TopicPartition`
offsets require does not arise. Because you only ever store after success,
"highest stored" and "everything that actually worked" are the same set — that,
and nothing else, is what makes a bare `commit()` safe here.

> Do not reach for `seek()` to "fix" a stored offset. `seek()` resets the *fetch*
> position and leaves the stored offset untouched — only `assign()` clears it.
> librdkafka's own guidance is blunt: *avoid storing offsets after calling
> `seek()`*. This design never calls `seek()` at all (§7.1).

Commit **synchronously** (`asynchronous=False`). Fire-and-forget would defeat the
point: you would move to the next message without knowing the previous one's
offset is durable, reopening the window this section exists to close.

**The failure this replaces:** a single shared "last message" passed to
`commit(message=msg)` advances only *that* message's partition. Batch fetch makes
that worse, not better — one `consume()` call routinely returns messages from
several partitions at once. It was reproduced against an 8-partition topic where
7 of 8 partitions never committed a single offset.

### 6.2 An offset is stored and committed only after its handler succeeds

No exceptions. Never store before processing; never store a message abandoned for
a transient reason. See §7 for the success / skip / failure classification — a
**skip** is a success for offset purposes (the message will never be processable,
so commit it and move on); a **failure** is not.

### 6.3 A batch is not an atomic unit

`consume_batch()` returns up to `KAFKA_BATCH_SIZE` messages spanning arbitrary
partitions. They are processed, stored and committed **one at a time, in order**.
The batch is a fetch optimisation, nothing more — it never becomes a unit of
work, a transaction, or a commit boundary.

Every element must be checked with `msg.error()` before use. **Only a fatal error
may take the process down:**

| `msg.error()` | Action |
|---|---|
| `None` | A real message. Process it. |
| `KafkaError._PARTITION_EOF` | Informational end-of-partition, not a failure. Skip. (Only delivered if `enable.partition.eof` is on; handle it anyway.) |
| `err.fatal()` is true | Unrecoverable. Raise, exit non-zero, let the orchestrator restart. |
| anything else | Log at `ERROR` and **continue the loop**. Do not raise. |

The last row is not defensiveness, it is a bug fix. An earlier draft raised
`KafkaException` on any non-EOF error entry, which crash-loops the process on
transient conditions — most sharply on `_MAX_POLL_EXCEEDED`, which is precisely
the error you receive *because* you were slow, and which restarting makes worse.

Do not use `err.retriable()` as the discriminator either. Measured against
confluent-kafka 2.15.0, `KafkaError(_MAX_POLL_EXCEEDED)` reports
`retriable() == False` and `fatal() == False` — so a `retriable()`-based rule
would let it through to the raise branch. `fatal()` is the only safe trigger.

Sequential commit is what makes §7.2 simple: when a handler fails on partition
*P* partway through a batch, everything before it on *P* is **already committed**,
so abandoning the rest of *P*'s messages loses nothing and re-processes nothing.
Other partitions in the same batch continue unaffected.

### 6.4 The in-flight window, and the revocation fence

This is the hazard bulk fetch actually introduces, and per-message commit does
not address it.

**The gap.** `consume(num_messages=N)` moves the *fetch* position forward by up
to N in a single call — those messages are dequeued into this process. The
*committed* position then crawls forward one message at a time. Partition
ownership can change in between, and the messages you are still holding do not
know that.

**Walkthrough.** A batch of 100 contains 50 messages from partition `p3`,
offsets 400–449.

```
you process p3 400–419, committing each          → committed = 420
── rebalance: another replica joins, p3 revoked from you ──
replica B is assigned p3 and starts from 420
you still hold p3 420–449 in memory and keep processing them
```

Both consumers now process offsets 420–449. **Double billing.** Your commits for
`p3` also begin failing with `_ASSIGNMENT_LOST`, so you cannot even record what
you did. The same shape arrives via `max.poll.interval.ms`: overrun the interval,
get kicked, partitions reassigned, and keep chewing the in-memory batch.

**The fence.** `on_revoke` and `on_lost` (§6.5) record the revoked partitions and
bump a generation counter on `ManagedConsumer`. The loop asks **before every
message**:

```python
for msg in await consumer.consume_batch():
    if not consumer.owns(msg):      # ← the fence
        continue                    # partition revoked mid-batch; drop the rest
    ...
```

That shrinks exposure from "up to `KAFKA_BATCH_SIZE` messages" to "the one
message in flight when the revocation landed".

**It does not eliminate it, and no commit strategy can.** During a rebalance both
the old and new owner can briefly believe they own a partition — the old owner
has not yet processed the revocation. Kafka has no mechanism that prevents this
against an external system. The fence is a necessary mitigation, not a guarantee.

**The remaining guard lives at the sink**: the debit is gated on the span key not
already being present, in the same SQL statement that performs it, so a duplicate
is *rejected by Postgres* rather than prevented by timing. See §8.2 — it is a
precondition for running more than one replica, and the fence alone does not
substitute for it.

Two consequences worth stating:

**This is why `KAFKA_BATCH_SIZE` defaults to `1`.** At a batch of one there is
nothing held when a revocation lands, so the fence is airtight and the window is
zero. It also sidesteps librdkafka's batch-API rebalance hazard entirely (§11),
which applies only above one.

The batch machinery is kept, not removed: `consume(num_messages=N)` is still the
call, `KAFKA_BATCH_SIZE` is still the knob, and raising it is a config change
rather than a rewrite. **Two things must be true before raising it:**

1. The write-time guard (§8.2) exists, so a concurrent duplicate is rejected by
   Postgres rather than merely narrowed by the fence.
2. Reconciliation (§7.5) is running, so messages lost to the batch-API hazard are
   detected rather than silently unbilled.

Until both hold, a larger batch trades a real correctness margin for a fetch
saving that §6.8 shows is small in steady state.

### 6.5 Rebalance callbacks — where correctness actually lives

`ManagedConsumer` defines `on_assign`, `on_revoke` and `on_lost` and passes them
to `subscribe()`. They are not optional hooks; without them a rebalance silently
duplicates or loses processing.

**Assignment strategy: `partition.assignment.strategy = cooperative-sticky`.**
The eager strategies (`range`, `roundrobin`) revoke *everything* from *everyone*
on any membership change and redistribute — a stop-the-world pause for the whole
group because one member joined. Cooperative-sticky is incremental: consumers
keep what they already hold and only the partitions that must move are revoked.
That matters here precisely because one consumer holds many partitions — a new
member needing one partition should not stall the other seven.

**None of the three callbacks commits anything.** Per-message commit (§6.1) means
there is never a pending offset to flush, so a "backstop" commit has nothing to
do — and a bare `commit()` here is actively harmful: with nothing new stored it
raises `KafkaException(_NO_OFFSET)` (verified against confluent-kafka 2.15.0),
and during a revoke it can also raise `_ASSIGNMENT_LOST`. Either exception
propagates out of `consume()` and takes down the process on every rebalance and
every clean shutdown. The callbacks record state; they do not talk to the broker.

| Callback | When | What to do |
|---|---|---|
| `on_assign` | Partitions granted | Add them to the assigned set and bump the generation. Under cooperative-sticky the list contains only the **newly added** partitions, not the full assignment — do not reset state for partitions you still own. Call `incremental_assign(partitions)`. |
| `on_revoke` | Clean loss — a member joined or left | Remove them from the assigned set, bump the generation, drop their retry state. **No commit.** The fence (§6.4) stops the loop touching them; anything uncommitted is redelivered to whoever picks the partition up. Call `incremental_unassign(partitions)`. |
| `on_lost` | Partitions lost **without** a clean revoke — `session.timeout.ms` or `max.poll.interval.ms` exceeded | Same state changes, logged at `ERROR`. **Emphatically no commit** — another consumer may already own the partition and be ahead of you, and committing would overwrite its progress. |

The `on_revoke` / `on_lost` distinction still matters, but it is now about
severity and logging rather than about whether to commit: neither commits, and
`on_lost` means work was very likely processed twice, so it deserves an alert.

**Cooperative-sticky changes which assign API is legal.** Under
`COOPERATIVE` protocol the callbacks must call `incremental_assign()` /
`incremental_unassign()`, never `assign()` / `unassign()`. Getting this wrong is
not a clean error: the Python binding auto-applies the assignment only when the
callback made *no* assign call, so a callback that *attempted* `assign()` sets
the "already assigned" flag, the fallback does not fire, and the consumer is left
with an unsynchronised assignment — **wedged, not crashed**. If a callback
raises, the fallback *does* fire, so the rebalance takes effect and *then* the
exception surfaces out of `consume()`.

Both callbacks must also drop any per-partition retry state from §7.1 — a retry
counter for a partition you no longer own is stale and would suppress processing
if that partition came back.

**Rebalances are routine, not rare.** With multiple deployments per consumer
(§8), every deploy, scale event, pod eviction and liveness restart is a
rebalance. These callbacks and the §6.4 fence are on the hot path for normal
operations, not just for failures.

### 6.6 Blocking calls go through the consumer's single-worker executor

`consume()`, `commit()` and `store_offsets()` are blocking librdkafka calls,
routed through `ManagedConsumer`'s `ThreadPoolExecutor(max_workers=1)` by the
async wrappers. Do not call the inherited synchronous methods directly from the
event loop.

Rebalance callbacks are the exception: librdkafka invokes them on the thread that
is inside `consume()`. Keep them synchronous, short, and free of `await` — a
callback that blocks on the event loop from inside the executor thread will
deadlock. Since they only mutate the assigned set and the generation counter
(§6.5), that constraint costs nothing.

The fence's state is therefore **written on the executor thread and read on the
event loop**. Plain attribute assignment of a `set` and an `int` is adequate
under the GIL; no lock is needed, and adding one would risk the deadlock above.
The single worker is also what satisfies librdkafka's requirement that the batch
API and any seek/pause/resume be called in *sequential order* (§11).

**Do not use `confluent_kafka.aio.AIOConsumer.`** It binds its background-thread →
event-loop callback bridge via the deprecated `asyncio.get_event_loop()`
([confluentinc/confluent-kafka-python#2211](https://github.com/confluentinc/confluent-kafka-python/issues/2211),
open/unfixed), which can silently attach to the wrong loop — `await consumer.poll()`
then hangs forever with no error, no exception, and no log line. `ManagedConsumer`
exists precisely so every blocking call is pushed onto an executor explicitly.

### 6.7 Timeouts bound three different things

| Setting | Bounds |
|---|---|
| `KAFKA_POLL_TIMEOUT_S` (1.0) | How long one fetch blocks. Also bounds shutdown latency — an in-flight fetch is not interrupted by the signal handler. Keep it small. |
| `KAFKA_SESSION_TIMEOUT_MS` | How long the broker waits for a heartbeat before declaring the consumer dead. Exceeding it means `on_lost`, not `on_revoke` — uncommitted work is redelivered elsewhere. |
| `KAFKA_MAX_POLL_INTERVAL_MS` (300 s) | How long between fetches before the group assumes you are stuck. Processing a whole batch happens *between* fetches. |

The constraint that follows is hard, not advisory: **`KAFKA_BATCH_SIZE` ×
worst-case per-message time must stay comfortably under
`KAFKA_MAX_POLL_INTERVAL_MS`.** Overrunning it means the partitions are taken
away as `on_lost` while this process is still holding and processing their
messages — §6.4's double-processing scenario, self-inflicted.

**A trap worth naming: committing does not reset the poll-interval timer.** Only
queue-serving calls do. A loop that commits busily but fetches rarely will still
be evicted; only the next `consume()` restarts the clock.

### 6.8 What per-message commit costs

One broker round-trip per message instead of one per batch. That is a real cost,
accepted deliberately, and worth stating accurately rather than optimistically:

- **A consumer group's commits serialize onto a single `__consumer_offsets`
  partition**, chosen by hashing `group.id`. Per-message commit at N msg/s is N
  replicated writes/s onto one partition leader.
- **`offsets.commit.timeout.ms` defaults to 5 s** and the commit is acked only
  once the replicas have it — so commit latency tracks replication, not
  round-trip time.
- **Commits are subject to KIP-124 request-rate quotas.** Under broker load a
  synchronous commit can be throttled, stalling the loop directly.

It is affordable here because the commit is small next to the work it protects:
this consumer already does a database write, and sometimes an outbound HTTP call,
for every message.

**The bulk-fetch win is narrower than it looks, which is why the default batch
size is 1.** `consume()` returns as soon as *any* message is available — it does
not wait to fill `num_messages`. In steady state you would get batches of one to
three regardless of the setting, so a large `KAFKA_BATCH_SIZE` buys almost
nothing until the consumer is genuinely behind. Weigh that against what it costs:
a non-zero in-flight window (§6.4) and librdkafka's batch-API rebalance hazard
(§11). The machinery stays so catch-up throughput is one config change away once
§6.4's two preconditions hold.

**Per-message commit is not negotiable for a consumer with money side effects.**
An earlier draft offered a carve-out letting a commit-bound consumer batch its
commits; that carve-out is withdrawn. A batch-sized commit window is a
batch-sized duplicate-side-effect window on crash (§6.1), and the tradeoff was
stated in terms of idempotency, which does not cover it.

---

## 7. Error and offset semantics

Three outcomes, and they must be kept distinct. Conflating them is the root of
both offset bugs the old code carried.

| Outcome | Meaning | Offset |
|---|---|---|
| **Success** | Handler returned | Stored and committed immediately (§6.1) |
| **Skip** | Message is not for us, or is permanently malformed | Recorded and committed — retrying cannot help |
| **Failure** | Transient: infrastructure unavailable, unexpected error | **Not** recorded; the message is retried (§7.1) |

### 7.1 A failed message must actually be retried

The old loop only did `continue` on a handler exception, without recording the
offset. That looks correct but isn't: a *later* message on the same partition
records a higher offset, so the failed message gets committed past and is never
redelivered — the opposite of what its own comments and the README claimed.

**Required behaviour** on handler failure — retry the **in-hand `Message`
object**, in place. There is no rewind:

1. Retry the same `msg` up to **3 attempts**, `1s / 2s / 4s` backoff.
2. If one succeeds, store and commit it and carry on with the batch.
3. On exhaustion, log at `CRITICAL` with topic, partition, offset and the raw
   payload, then store and commit to move past it.

```python
async def handle_with_retry(msg) -> None:
    for attempt in (1, 2, 3):
        try:
            return await handle(msg)
        except Transient as exc:
            if attempt == 3:
                logger.critical("giving up | %s[%d]@%d payload=%r: %s",
                                msg.topic(), msg.partition(), msg.offset(),
                                msg.value(), exc)
                return
            await asyncio.sleep(2 ** (attempt - 1))
```

**Why no `seek()`.** Rewinding was the original design and it is unnecessary: the
crash case is already covered because an unstored offset is never committed, so a
restart resumes at exactly that message. Removing `seek()` also removes
librdkafka's *"avoid storing offsets after calling `seek()`"* ordering rule, the
`seek`-versus-stored-offset subtlety (`seek()` moves the fetch position and
leaves `rktp_stored_pos` alone — only `assign()` clears it), and one of the two
conditions in librdkafka's batch-API thread-safety warning (§11).

**The tradeoff, stated plainly:** retrying blocks that partition for up to 7
seconds, and giving up after 3 attempts drops a message. Bounded-retry-then-skip
is chosen because a permanently stalled billing partition loses the data anyway
once topic retention expires — and does so with no `CRITICAL` line for anyone to
act on. Recovery from that line is manual replay.

**The window this leaves.** A transient outage longer than ~7 seconds — a Redis
failover, a Postgres restart — exhausts the ladder and drops every message that
arrives during it. §7.3 classifies infrastructure errors as failures precisely so
they are retried rather than silently skipped, but the ladder is short. This is
the strongest argument for a dead-letter queue when one is added (§11).

### 7.2 Partial batch failure

In-hand retry (§7.1) resolves each message before the loop moves on, so a failure
no longer leaves later messages of the same partition in an ambiguous state — by
the time the loop advances, the failed message has either succeeded or been
committed past with a `CRITICAL` line.

That leaves exactly one case where the rest of a partition's messages must be
abandoned mid-batch: **the partition was revoked** (§6.4). The `owns()` fence
handles it, and it applies per partition — other partitions in the same batch
keep going, because they are independent and still owned.

Do not abandon the whole batch when one partition is revoked. The others are
unaffected, and dropping them would re-fetch work that was never at risk.

### 7.3 Infrastructure failure is not a skip

The old PPU handler returned `None` from its Redis dedup check on *any* Redis
error, and the caller treated that identically to "already billed": the event
was dropped **and** its offset committed. Every Redis blip was unrecoverable
revenue loss.

Separate malformed input from infrastructure failure:

| Condition | Classification | Action |
|---|---|---|
| Empty dedup key (span has no `correlation_id`) | **Skip** | Warn and skip permanently — retrying cannot help. Unreachable in practice: `inference-service/trace/setup.py` already drops spans with no `correlation_id`. |
| Dedup key exists | **Skip** | Duplicate; already billed. |
| Dedup key absent | proceed | Bill. |
| Redis error during the dedup check | **Proceed** | Warn and bill. The write-time guard (§8.2) is the authority; Redis is only the fast path. |
| Postgres error during the billing write | **Failure** | Raise. Retried by §7.1. |

**The Redis row changes meaning once §8.2 ships, and it is worth being explicit
about why.** While Redis dedup is the *only* guard, an error there has no good
answer: proceed and risk double-billing, or fail and stall. Once the debit is
gated in SQL, the question dissolves — a duplicate that slips past a
Redis outage is rejected by the guard, so the correct action is to warn and carry
on. Retrying would stall billing for the duration of a Redis incident to protect
against something Postgres already prevents.

Until §8.2 lands, treat a Redis error as a **Failure** instead: with no
authoritative guard behind it, retrying is the lesser risk. This is the one place
in §7 whose classification depends on which of the two has shipped.

The general rule is unchanged: an error reaching *the store that owns the truth*
is a failure. After §8.2 that store is Postgres, not Redis.

### 7.4 Delivery guarantee

At-least-once. Three separate mechanisms bound three separate exposures, and it
matters which covers what:

| Exposure | Bounded by | To |
|---|---|---|
| **Crash** — process dies after a side effect, before its commit | Per-message commit (§6.1) | One message |
| **Rebalance** — partition reassigned while its messages are held | The `owns()` fence (§6.4) | One message: the one in flight when the revocation landed |
| **Concurrency** — old and new owner both believe they hold the partition | **Nothing in Kafka.** Only a guard at the sink (§8.2) | Rejected at write time, within the guard's `N`-key window |

The third row is the important one. The first two are *narrowing* mechanisms —
they shrink windows, they do not close them, and no commit strategy can, because
during a rebalance the losing consumer has not yet learned it lost. Handlers must
therefore be idempotent regardless of how tight the first two are.

Note the third row's bound is not "zero". §8.2's guard is a bounded set, not a
unique constraint: a duplicate arriving after `N` other billings for the same
tenant is not rejected. That residue is what reconciliation (§7.5) exists to
catch.

The PPU handler's Redis dedup key — a 1-hour cache entry on an LRU instance — is
adequate as a fast path against the one-message windows, and **not** adequate as
the guard against concurrent processing. §8.2 specifies what is.

### 7.5 Reconciliation — the backstop for what slips through

Everything above bounds *duplication*. Nothing above detects **loss**, and this
pipeline has three ways to lose a billable span:

| Loss path | Where |
|---|---|
| Retry ladder exhausted — message committed past after a `CRITICAL` | §7.1 |
| librdkafka's batch API dropping messages during a rebalance | §11, live only if `KAFKA_BATCH_SIZE > 1` |
| Any future handler bug that classifies a real message as a skip | §7 |

None of them is visible from inside the consumer: a message that never arrives
leaves no trace, and a `CRITICAL` line only helps if somebody reads it.

**A nightly reconciliation job closes all three with one mechanism, and needs no
new storage.** The two sides already exist and are genuinely independent:

| Side | Source | Grain |
|---|---|---|
| What *should* have been billed | OpenSearch `traces-*` | per span |
| What *was* billed | `ppu_quota_usage.units_used` / `cost_accum` | per `(tenant, inference_name, billing_month, tier_id)` |

The independence is real: Fluent Bit and the PPU consumer are two separate sinks
off the same Kafka topic (`kafka-topic-otel-trace`), so a fault in one does not
corrupt the other.

Because the Postgres side is a monthly rollup, this is **aggregate**
reconciliation. Sum billable units per `(tenant, service_id)` from `traces-*`,
join `mm_services` for `task_type`, apply the LLM-vs-rest unit rule, and compare
against `units_used`. A non-zero delta means something was lost or double-billed.

**It tells you *that* there is drift, not *which* span caused it.** That is the
price of not keeping a per-span ledger, and it is why §8.2's guard exists — the
guard prevents the common case at write time, reconciliation catches what escapes
it.

**Run it after midnight, on the previous day's data.** Two reasons beyond low
traffic: `traces-*` is a **daily** index (`traces-YYYY.MM.DD`), so a closed day is
a complete, no-longer-written index; and it bounds drift correction to under 24
hours.

**Prerequisite: `traces-*` needs an explicit index template.** It currently has
none — only `logs-*` does
(`infrastructure/opensearch/index-template.json`, pushed by
`infrastructure/opensearch/init-opensearch.sh`). Consequences of leaving it
dynamic:

- Field types are re-inferred **per daily index**. `input_tokens` is seeded as
  int `0` and later carries floats, so one day may map `long` and the next
  `double`. If a non-numeric ever lands first, the field maps as `text`, every
  subsequent numeric document that day is **rejected at index time**, and Fluent
  Bit discards it after `Retry_Limit 5` — silent loss in the very store used to
  detect silent loss.
- Strings map as `text` with a `.keyword` subfield, so `attributes.tenantId` is
  analyzed. Billing filters must use `term` on `attributes.tenantId.keyword`, not
  `match_phrase`, or a tenant id containing `-` or `_` will match too broadly.

The template must pin `attributes.tenantId`, `attributes.service_id`,
`attributes.authType`, `context.span_id` and `context.trace_id` as `keyword`, and
the token counts as a single numeric type.

**Known coupling — the billing rules exist in two places.** The job must mirror
every filter the consumer applies, or it reports drift that is not real:

| Rule | Where |
|---|---|
| Skip unless `attributes.authType == "api_key"` (absent ⇒ bill) | `handler.py:140-146` |
| Skip when tenant, service, or total tokens are missing/zero | `handler.py:156` |
| Skip when `mm_services` has no pricing row, or cost computes to 0 | `_bill_usage`, `_billing.py` |
| LLM bills `input+output`; everything else bills `input` only | `_bill_usage` — driven by `mm_services.task_type`, **not** the span's `attributes.task_type`, which is observability-only |

Changing a billing rule means changing both. The alternative — extracting the
billable-units calculation into a shared pure function both call — is the right
fix if this drifts even once.

Also note `end_time` **is** present in the indexed document (Fluent Bit's `lift`
promotes it; a comment in `platform-core-service/app/routes/telemetry.py` claiming
otherwise is stale), so the job can derive `billing_month` exactly as
`_resolve_billing_month` does rather than approximating with `@timestamp`, which
is ingest time.

This is also what makes raising `KAFKA_BATCH_SIZE` above 1 defensible (§6.4):
with reconciliation running, the batch-API hazard becomes a detected condition
rather than silent lost revenue.

---

## 8. Running multiple replicas — gated on the write-time guard

Multiple deployments per consumer are expected. Kafka handles the mechanics: each
consumer has its own group id, and the coordinator spreads partitions across
whatever members are alive. What Kafka does **not** handle is two members briefly
processing the same offsets during a rebalance (§6.4) — which on a billing path
means charging a customer twice.

### 8.1 The gate

> **Replicas stay at `1` until the write-time guard below exists, together with
> the reconciliation job (§7.5) that backstops it. Once both ship, replicas may
> be raised.**

A hard gate, not a preference. Everything else in this section is what makes
lifting it safe.

### 8.2 The write-time guard — bounded recent-span keys

Redis dedup is not sufficient, and never was. The key
`ppu:billed:{correlation_id}:{span_id}` is checked *before* billing and set
*after* the database commit, so there is a window between them. With one process,
a crash in that window means redelivery to itself. With N processes, two replicas
can be inside it concurrently and **both bill**. The key also lives on an
`allkeys-lru` instance shared with `auth:apikey:*` and `core:service:*` under a
1-hour TTL (`Constants.PPU_BILLED_KEY_TTL`) — eviction under memory pressure
silently re-arms double billing.

The guard has to be **in the same statement as the debit**, so that the check and
the write cannot be separated by a rebalance. It does **not** need a separate
table: a bounded set of recently-billed span keys carried on the assignment row
itself is enough, because the row being guarded is the row being debited.

**Column.** Add to `ppu_tenant_tier_assignments`:

```sql
ALTER TABLE ppu_tenant_tier_assignments
    ADD COLUMN recent_span_keys text[] NOT NULL DEFAULT '{}';
```

`NOT NULL DEFAULT '{}'` is not cosmetic. With a NULL array, `:key = ANY(NULL)`
evaluates to NULL, `NOT NULL` is NULL, the `WHERE` clause fails to match, and
**every billing silently stops**. Adding a column with a non-volatile default is
metadata-only on PG 11+, so the migration does not rewrite the table.

**The guarded write**, replacing the `wallet_update` CTE in
`deduct_balance_and_update_quota` (`consumers/payperuse_consumer/_billing.py`):

```sql
WITH target AS (
    -- classification only: does an active assignment exist at all?
    SELECT id FROM ppu_tenant_tier_assignments
     WHERE tenant_id = :tenant_id
       AND effective_from <= now() AND effective_to > now()
),
wallet_update AS (
    UPDATE ppu_tenant_tier_assignments a
       SET available_balance = a.available_balance - :cost,
           recent_span_keys  = (ARRAY[:span_key] || a.recent_span_keys)[1:50],
           updated_at        = now()
      FROM target
     WHERE a.id = target.id
       AND NOT (:span_key = ANY(a.recent_span_keys))   -- ← the guard
    RETURNING a.available_balance, a.tier_id
),
quota_upsert AS ( ... )        -- unchanged, still fed by wallet_update
SELECT (SELECT count(*) FROM target) AS assignment_exists,
       wallet_update.available_balance, wallet_update.tier_id,
       quota_upsert.units_used, quota_upsert.monthly_quota_snap
  FROM ...
```

`:span_key` is `"{correlation_id}:{span_id}"` — the same composite the Redis key
already uses. **`correlation_id` alone is not sufficient**: one request can emit
several `ai-inference` spans under one correlation id (TTS chunks text over 400
chars into per-item Triton calls), so guarding on it alone would reject every
chunk after the first and *under-bill* the request. `handler.py:115-126` explains
this at length; the same reasoning applies here.

**Why this is atomic.** Under READ COMMITTED, a second `UPDATE` targeting the same
row blocks until the first commits and then **re-evaluates its `WHERE` clause
against the new row version**. So the loser of a race sees the winner's key
already in `recent_span_keys`, matches no row, and never debits. Postgres
arbitrates at write time; there is no undo because there was no write. This adds
no contention that did not already exist — the balance decrement already
serialized every billing for a tenant onto this row.

**Distinguishing "duplicate" from "no assignment" is mandatory.** Both produce
zero rows from `wallet_update`, but they mean opposite things, and the existing
caller treats a missing `tier_id` as *not entitled* — setting `quota_exhausted`
and firing the quota-exhausted notification to auth-service. A duplicate must not
do that. The `assignment_exists` count above is what separates them:

| `assignment_exists` | `wallet_update` row | Meaning | Action |
|---|---|---|---|
| 0 | none | No active tier assignment | Existing not-entitled path (§7 / `BillingWriteResult.tier_id is None`) |
| ≥ 1 | none | **Duplicate rejected by the guard** | Log at `DEBUG` and skip. No notification, no error |
| ≥ 1 | present | Billed | Normal path |

**Sizing `N` (the `[1:50]` slice).** The array must hold enough keys that a
redelivered span is still remembered when it comes back. The redelivery window is
short — one message per partition per rebalance (§6.4), reprocessed within
seconds — so `N` only has to exceed the number of billings **for that one tenant**
in that window. 50 is a reasonable start. Two constraints on going larger: keys
are ~55 bytes, so ~50 keys keeps the row near Postgres's ~2 KB TOAST threshold and
above that the array is stored out-of-line and rewritten on every billing; and a
duplicate older than `N` slips through, where it is caught by reconciliation
(§7.5) rather than prevented.

**Operational note.** This row is now rewritten on every billing event — it
already was, for the balance decrement, but each dead tuple is larger. Consider a
per-table `autovacuum_vacuum_scale_factor` low enough for a small, very
high-update table.

Note which operations this protects. Only two things in the billing path are
non-idempotent, and both are arithmetic inside this one statement:
`available_balance - :cost` and `units_used + :units`. Everything else is already
safe to repeat — `_notify_auth` POSTs `{"exhausted": true}` and
`{"inference_name": ...}`, which are state-sets, not increments.

Redis then demotes to a fast path in front of an authoritative check. It may be
stale, evicted, or entirely down without affecting correctness — only latency.
That also dissolves §7.3's awkwardness about Redis outages costing revenue.

Until this lands, the comment in `consumers/payperuse_consumer/handler.py` —
*"billing correctness relies on at-most-one consumer instance when Redis is
down"* — accurately describes a fragile design. Once it lands the comment is
false and must be removed.

> **Known limit, accepted deliberately.** This is a bounded guard, not a
> constraint: it cannot catch a duplicate that arrives after `N` other billings
> for the same tenant. That was the tradeoff taken to avoid a per-span ledger
> table. Reconciliation (§7.5) is the backstop, which is why the two ship
> together.

### 8.3 Rules for running N

| Rule | Why |
|---|---|
| Each consumer has its **own group id** | Two different consumers sharing a group would split one topic's partitions between unrelated handlers |
| **Replicas ≤ partitions** | Surplus members get no assignment and idle; partition count is the real parallelism ceiling |
| The **`owns()` fence** (§6.4) is mandatory | Without it, a rebalance leaves a whole batch being processed by two members at once |
| Rebalance callbacks **never commit** (§6.5) | `_NO_OFFSET` / `_ASSIGNMENT_LOST` would crash every member on every deploy |
| Handlers are **idempotent** (§7.4) | The residual one-message windows are irreducible |

### 8.4 What to expect operationally

Every deploy, scale event, pod eviction and liveness restart is a rebalance, and
each exercises §6.4 and §6.5. `cooperative-sticky` is what keeps a rebalance from
stopping the members that are *not* losing partitions — with several replicas
that is a real benefit, rather than the no-op it would have been at one member.

Per-replica throughput is unchanged: one serial, I/O-bound loop handling one
message at a time. Scaling is horizontal only, and bounded by partition count.

---

## 9. Security

- **Import injection.** `--consumer` feeds `importlib.import_module()`. The
  validation in §3.2 (regex **and** allow-list from the `consumers/` directory)
  is the guard. Do not relax it to accept dotted paths.
- **Secrets in the image — mitigated by `.dockerignore`.** The Dockerfile's
  `COPY . .` copies the whole build context, runs as root *before* the `chown` to
  `appuser`, and Docker layers are readable by anyone who can pull the image.
  A local `.env` sits in that context: it is **git**-ignored, which does nothing
  for a build. `services/kafka-consumers/.dockerignore` is what keeps it out.
- **Trust boundary.** This service calls auth-service `/internal/ppu/*`, which is
  service-to-service only and must never be publicly reachable. It also writes
  directly to the `ppu_*` tables in `ai4iplatform_core` with no in-process
  authorization — the process's network position *is* its authorization.
- The image runs as non-root `appuser`. Keep it that way.

---

## 10. Offset position is always an explicit decision

**Read this before choosing a `GROUP_ID`.**

Committed offsets belong to the consumer group. A **new** group id has none, and
what happens next is decided entirely by `auto.offset.reset`. With `earliest` it
replays every retained message; the PPU dedup TTL is one hour, so every replayed
span older than that has no dedup key and is **billed a second time**.

### 10.1 The silent case that forces `error`

Renaming a group is the *obvious* way to land in that state. There is also an
automatic one, and it gives no warning at all:

**`OFFSET_OUT_OF_RANGE` never reaches the application.** librdkafka routes it
internally and applies `auto.offset.reset` silently — an `_AUTO_OFFSET_RESET`
error entry is emitted **only** when the setting is `error`. So with `earliest`,
any of these replays the whole topic with no signal, no exception and no log line
the loop can act on:

- the consumer is down longer than the topic's `retention.ms`
- the topic is recreated
- an unclean leader election truncates the log
- partitions are added or the log start advances past the committed offset

Combined with §11's absence of lag metrics, nobody notices until wallets are
wrong. **This is why `KAFKA_AUTO_OFFSET_RESET` should be `error` (§3.1)** — the
reset becomes an alert and a human decision instead of a silent mass re-bill.

> **`[PLANNED]`** — the shipped default is still `earliest`, so the service is
> currently exposed to exactly the silent replay described above. Flipping it is
> tracked with the group-id migration in §10.2.

### 10.2 Why `payperuse_consumer` keeps the legacy group id

**`[SHIPPED]` — `GROUP_ID = "aio-python-consumers"`, unchanged and deliberately so.**

The group already holds committed offsets for the topic, and
`KAFKA_AUTO_OFFSET_RESET` is `earliest`. Renaming it would give the new group no
committed offsets, and `earliest` would then replay the whole topic from the
beginning and **re-bill every span still in retention**. The dedup TTL is one
hour, so anything older than that is billed a second time.

Keeping the id is safe today because the shipped consumer does not change the
assignment strategy: `build_consumer_config()` sets no
`partition.assignment.strategy`, so this process uses the same librdkafka
default (`range,roundrobin`) the old one did. There is no assignor mismatch and
a rolling restart rebalances normally.

Renaming the group is therefore an **operational change, not a code change**,
and it only becomes necessary once §3.1's `cooperative-sticky` lands — at that
point the old and new processes share no common assignor and a group cannot
form. Sequence it as: seed the new group's offsets from the old one *before* its
first start, with the old consumer stopped.

> **`[PLANNED]` — the runbook below applies only when the group id actually
> changes.** Nothing on this branch requires it. Do not run these commands as
> part of deploying this change; the existing group's offsets are already
> correct and seeding a group that never runs is wasted effort.

```bash
# Read the old group's current offsets
docker exec ai4v-kafka kafka-consumer-groups --bootstrap-server localhost:9093 \
    --group aio-python-consumers --describe

# Seed the new group to the same position
docker exec ai4v-kafka kafka-consumer-groups --bootstrap-server localhost:9093 \
    --group <new-group-id> --topic <topic> --reset-offsets --to-current --execute

# Verify BEFORE starting the consumer
docker exec ai4v-kafka kafka-consumer-groups --bootstrap-server localhost:9093 \
    --group <new-group-id> --describe
```

Use `--to-offset <n>` per partition if `--to-current` does not resolve to the old
group's committed position in your broker version. Verify, then start.

A refusal to start on a group you *believe* is seeded is the safety net working:
check the seeding rather than switching the setting back to `earliest`.

---

## 11. Known gaps

Recorded deliberately. None are addressed by this redesign. Test coverage is not
listed here — it is part of the design, in §3.6 and §5.

- **No dead-letter queue — deliberately out of scope at this stage.** §7.1's
  exhausted-retry path terminates in a `CRITICAL` log line carrying the raw
  payload, and recovery is manual replay from it. Reconciliation (§7.5) covers
  the *detection* half of what a DLQ would give — a dropped span shows up as a
  billing shortfall against `traces-*` — so what is missing is the automatic
  requeue, not the visibility.
  Revisit if the `CRITICAL` line fires often enough that manual replay stops
  being practical.
- **Batch fetch is not safe against concurrent rebalancing.** librdkafka's own
  known issues, for the version pinned here:

  > The Consumer Batch APIs … are not thread safe if `rkmessages_size` is greater
  > than 1 and any of the **seek**, **pause**, **resume** or **rebalancing**
  > operation is performed in parallel … **Some of the messages might be lost, or
  > erroneously returned to the application.**

  The single-worker executor (§6.6) serializes every app-driven call, and this
  design no longer calls `seek()` at all (§7.1) — so the app-driven half of that
  condition is satisfied. **Rebalancing is not app-driven and cannot be
  serialized**, so the only way to escape the condition is `num_messages == 1`.

  **Mitigated, not open:** `KAFKA_BATCH_SIZE` defaults to `1`, which puts the
  hazard out of reach. It returns the moment that setting is raised, which is why
  §6.4 gates raising it on the write-time guard (§8.2) and reconciliation (§7.5).
  Listed here because the knob exists and the risk is one config change away.
- **No metrics.** `ai4i_core.observability` is installed and never imported.
  There is no consumer-lag, processing-latency, error-rate or DLQ
  instrumentation, and no health endpoint. The Docker `HEALTHCHECK` greps
  `/proc/1/cmdline` — process liveness only, not broker/DB/Redis connectivity and
  not lag. Now that one image runs several roles it should also match the
  consumer name. (Broker connectivity itself is no longer blind — `error_cb` and
  `logger=` in §3.1 surface it — but lag still is.)
- **Duplicate-billing window** between `db.commit()` and the Redis dedup `set`.
  Closed by the write-time guard in §8.2; live until it ships, which is what the
  §8.1 replica gate exists for.
- **The write-time guard is bounded, not absolute** (§8.2). A duplicate arriving
  after `N` other billings for the same tenant is not caught, and falls through to
  reconciliation. That is the accepted cost of not keeping a per-span ledger
  table.
- **Billing rules are duplicated** between the consumer and the reconciliation
  job (§7.5). Changing one without the other produces phantom drift.
- **Loop logic is copied, not shared** (§3.5). Watch for the second consumer: a
  byte-identical loop is the signal to promote it into `bootstrap/`.
- **Log context is empty.** `ContextFilter` injects `trace_id` / `tenant_id` from
  contextvars, but nothing in this process sets them (`RequestMiddleware` is
  FastAPI-only), so every line carries null trace context and the formatter
  generates a fresh `trace_id` per line. Setting `trace_id` per message from the
  span's `correlation_id` would make consumer logs correlate with inference logs.

---

## 12. Adding a new consumer **`[PLANNED]`**

> **This is the target procedure and cannot be followed as written today** — it
> calls for `bootstrap/config.py`, `ManagedConsumer.build_bulk_message_consumer`
> and `infra()`, none of which exist. For the procedure that works against the
> current tree, see *Adding a consumer* in [README.md](./README.md).

1. Create `consumers/<name>_consumer/` with an **empty** `__init__.py`.
2. Add `config.py` for that consumer's topic and any service URLs. Nothing goes
   into `bootstrap/config.py`.
3. Add the handler — a plain async function taking a `confluent_kafka.Message`.
   No decorator, no registration.
4. Add `main.py` with a hardcoded `GROUP_ID` and `async def run()`. Build the
   consumer with `ManagedConsumer.build_bulk_message_consumer(...)`, wrap the
   lifecycle in `infra()`, and copy the loop from
   `consumers/payperuse_consumer/main.py` — honouring every invariant in §6 and
   §7.
5. Add `tests/` inside the package, covering the handler, the config, and the
   loop policy you just copied (§5). The copied loop is the part no shared code
   enforces — test it here or nothing does.
6. **Seed the new group's offsets before first start** (§10). Because
   `auto.offset.reset` is `error`, a group that has never committed will refuse
   to start — deliberately, so that where a consumer begins reading is always a
   decision someone made.
7. Add a deployment unit running the shared image with
   `--consumer <name>_consumer` and `replicas: 1` (§8.1).

There is no root `main.py` to edit and no registry to update. If
`consumers/<name>/main.py` exists with a callable `run`, the launcher can run it.

If step 4 produces a loop identical to the reference implementation's, promote it
into `bootstrap/` and have both consumers call it.
