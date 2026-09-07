# kafka-consumers — Architecture Changes

> ## ⚠️ Status: shared code shipped, `payperuse_consumer` not yet migrated
>
> **The split runs down the middle of this document, and there is a second,
> orthogonal split: code vs. tests.** Everything reusable — `bootstrap/` and its
> four modules, `ManagedConsumer`, `infra()`, `session_scope()`,
> `shutdown_event()` — is built. **None of it is tested on this branch.** A
> prototype suite exists on disk at `tests/` (§3.6), but `git status` shows
> `?? tests/` — it is untracked, not part of any commit, and must not be cited as
> shipped coverage until it is added. The one consumer that exists has **not**
> been moved onto `bootstrap/`: `payperuse_consumer` still reads the superseded
> service-root `config.py`, still builds a plain `confluent_kafka.Consumer`, and
> still runs the single-message poll loop it was moved with. Sections are tagged
> **`[SHIPPED]`** / **`[PLANNED]`** accordingly — the test suite is `[PLANNED]`
> throughout this document regardless of what exists untracked on disk. When in
> doubt, the code wins, and untracked files are not code.
>
> **What is shipped today:**
>
> | Described in this doc | Reality on this branch |
> |---|---|
> | One process per consumer, selected by `--consumer <name>` (§4) | Shipped. |
> | `bootstrap/` package — `config.py`, `launcher.py`, `lifecycle.py`, `consumers.py` (§3) | Shipped. `__init__.py` re-exports the public surface lazily via PEP 562, so `import bootstrap.launcher` does not pull in `bootstrap.config`. Its tests are not (§3.6). |
> | Root `main.py` is a three-line delegation to `bootstrap.launcher.main()` (§4) | Shipped. |
> | `ManagedConsumer`, `build_bulk_message_consumer()`, `infra()`, `add_database()`, `session_scope()`, `shutdown_event()` | Shipped, in `bootstrap/consumers.py` and `bootstrap/lifecycle.py`. |
> | `consumers/registry.py` removed — no `TOPIC_REGISTRY`, no `@kafka_listener`, no `KafkaRegistry` | **Deleted.** Handlers are plain async functions; `consumers/__init__.py` and `consumers/payperuse_consumer/__init__.py` are both empty, with no side-effect import. |
> | `cooperative-sticky`; an `error_cb` / `logger=` | Shipped **in `bootstrap/config.py`**. Not in the root `config.py`, which is what `payperuse_consumer` reads — see the row below. |
> | Rebalance callbacks, the assignment state behind `owns()`, the revocation fence (§6.4/§6.5) | Shipped in `ManagedConsumer`. No consumer exercises them yet, and nothing tests them (§3.6). |
>
> **What is NOT built yet** — every mention of these below is aspirational:
>
> | Described in this doc | Reality on this branch |
> |---|---|
> | A committed test suite for the shared code (§3.6) | **Not shipped.** A prototype exists locally at `tests/unit/bootstrap/` (75 cases collected, all passing, no broker/DB/Redis needed) but it is untracked. Nothing in `bootstrap/` is verified by anything this repository actually tracks. |
> | `payperuse_consumer` assembled from `bootstrap/` | It is not. `main.py` and `handler.py` import the service-root `config.py`; `run()` calls `ai4i_core.bootstrap.init_database` / `init_redis` / `close_database` directly rather than `infra()`, and builds a plain `Consumer` from the root module's `build_consumer_config()`. |
> | The service-root `config.py` deleted | Still present, and still the only settings module `payperuse_consumer` reads. Its docstring records the deliberate disagreements with `bootstrap/config.py`. |
> | `payperuse_consumer` gets its own `config.py` and its own tests | Neither exists. `TOPIC_PAY_PER_USE`, `AUTH_SERVICE_URL` and `Constants` are still on the root module, and the consumer package is entirely unasserted. |
> | `KAFKA_AUTO_OFFSET_RESET` defaulting to `error` anywhere | **Not shipped in either module.** `bootstrap/config.py` also defaults to `earliest` now — the exposure in §10.1 is live for `payperuse_consumer` *and* for any consumer built via `bootstrap/config.py`, migrated or brand-new, unless its `.env` explicitly overrides the variable. |
> | `enable.auto.offset.store=False` in `bootstrap/config.py` | **Not shipped.** Removed from `build_consumer_config()` in the same edit as the row above. `ManagedConsumer`'s per-message-commit guarantee (§6.1) does not hold without it — see the live-defects list above. |
> | `cooperative-sticky` **for `payperuse_consumer`** | The root `build_consumer_config()` sets no assignor, so that process uses librdkafka's default (`range,roundrobin`). This is load-bearing for §10.2. |
> | A new, descriptive consumer group id | `GROUP_ID = "aio-python-consumers"` — the legacy id, deliberately retained (§10.2). |
> | Batch fetch, the `owns()` fence, per-message commit (§6.1), `store_offsets()`/`commit()`, no `pending_offsets` dict | **The shipped loop does the opposite** — single-message `poll()`, and commits batched every 100 messages or 5 seconds via an explicit `pending_offsets` dict. See the §6 banner. |
>
> Sections §6–§9 describe invariants for the **target** loop. The shipped
> `payperuse_consumer` loop satisfies §6.6–§6.7 and **knowingly departs from
> §6.1/§6.8**.
>
> **Three live defects.** These are not "planned work" — they are bugs in
> shipped code that earlier revisions of this document described in the past
> tense as though already fixed:
>
> 1. **A failed message is dropped, not retried** (§7.1). `pending_offsets` is a
>    per-partition high-water mark, so the next *successful* message on a
>    partition commits past one whose handler raised. The loop's own comment says
>    the opposite.
> 2. **A Redis outage drops spans instead of billing them** (§7.3).
>    `_is_already_billed` returns `None` on any Redis error and the caller treats
>    `None` as "already billed" — the span is skipped and committed, while the log
>    line claims it is "proceeding without dedup".
> 3. **`bootstrap/config.py` no longer sets `enable.auto.offset.store=False`**
>    (§6.1, §10). It was removed along with the `error`-default safety fix in
>    the same edit. This is in the *shared* code, not `payperuse_consumer`'s loop
>    — it means `ManagedConsumer.build_bulk_message_consumer()` (§3.4), still
>    tagged `[SHIPPED]`, no longer satisfies the per-message-commit guarantee
>    §6.1 describes it as providing. A consumer built exactly as §12 instructs
>    today inherits the same "commits past a failed message" bug as (1), plus
>    the silent-replay exposure of (§10.1) on first start, unless its author
>    manually overrides `KAFKA_AUTO_OFFSET_RESET=error` in its own environment.
>
> None of the three is addressed on this branch. Read §6.1, §7.1, §7.3 and §10
> before touching the offset handling in either the shared code or a consumer's
> loop.

---

## 1. Changes

### The old flow (removed on this branch)

One process, one consumer group (`aio-python-consumers`, hardcoded in the root
`main.py`), one `confluent_kafka.Consumer` subscribed to **every** topic in a
module-global `TOPIC_REGISTRY`, with the poll loop living in the root `main.py`
itself. Handlers registered themselves with a `@kafka_listener("topic")`
decorator (`consumers/registry.py`) and were wired in by a side-effect import. A
`KafkaRegistry` routed each polled message to the handler registered for its
topic.

### The flow today **`[SHIPPED]`**

**One process per consumer.** Each consumer package owns a `main.py` exposing
`async def run()` and hardcodes its own consumer group id. The service-root
`main.py` is a three-line delegation to `bootstrap.launcher.main()`, which takes
`--consumer <name>` from deployment, validates the name against the `consumers/`
directory, configures logging, imports `consumers.<name>.main`, and calls
`run()`.

**The topic registry is gone.** `consumers/registry.py` — `TOPIC_REGISTRY`,
`kafka_listener`, `KafkaRegistry` — is deleted. With one process per consumer it
held a single entry and could only ever resolve to that consumer's own handler,
so the indirection bought nothing: the subscription is a property of the
consumer's module (a `TOPIC` constant, or the `topic=` argument to
`build_bulk_message_consumer`), and handlers are plain async functions taking a
`confluent_kafka.Message`. No decorator, no registration, no side-effect import
— `consumers/__init__.py` and `consumers/payperuse_consumer/__init__.py` are both
empty.

**Everything reusable lives in `bootstrap/`** — the launcher, shared
infrastructure settings, process lifecycle (database, Redis, signals), and
`ManagedConsumer`, a `confluent_kafka.Consumer` subclass that encapsulates
construction, subscription, rebalance callbacks and the async wrappers over
librdkafka's blocking calls. Any abstraction shared by more than one consumer
belongs there and nowhere else.

**`payperuse_consumer` has not been migrated onto it.** It still reads the
service-root `config.py`, still builds a plain `Consumer` from that module's
`build_consumer_config()`, and still runs the single-message loop with batched
commits it was moved with. Both shapes are drawn below; the second is what a new
consumer should look like.

```
                    deployment
                        │  --consumer payperuse_consumer
                        ▼
        ┌────────────────────────────────────────────┐
        │  main.py  →  bootstrap.launcher.main()     │
        │    argparse → validate name → --list       │
        │    configure_logging()                     │
        │    importlib → asyncio.run(run())          │
        └───────────────────┬────────────────────────┘
                            ▼
        ┌────────────────────────────────────────────┐
        │  consumers/payperuse_consumer/main.py      │
        │    GROUP_ID = "aio-python-consumers"       │
        │    TOPIC = settings.topics.TOPIC_PAY_PER_USE
        │    run():                                  │   ← still on the
        │      init_database() / init_redis()        │     service-root
        │      consumer = Consumer(                  │     config.py, not
        │          build_consumer_config(GROUP_ID))  │     on bootstrap/
        │      consumer.subscribe([TOPIC])           │
        │      while not shutdown:                   │
        │        msg = await poll()                  │
        │        handle_ppu_usage(msg)               │
        │        → batched commit (100 msgs / 5s)    │
        └───────────────────┬────────────────────────┘
                            ▼
        consumers/payperuse_consumer/handler.py  →  _billing.py
```

### The target flow — what a new consumer looks like **`[SHIPPED]`**

The shared code below is all built. What is `[PLANNED]` is only
`payperuse_consumer` adopting it (§5), and with it the deletion of the
service-root `config.py`.

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

## 2. File layout

**The current tree.** Deviations from the original target are marked. Three of
the `[PLANNED]` lines are the same piece of work — migrating `payperuse_consumer`
(§5). The `tests/` line is a **separate**, unrelated piece of unfinished work: a
committed test suite for this service (§3.6).

```
services/kafka-consumers/
├── main.py                       # 3-line entrypoint → bootstrap.launcher.main()
├── config.py                     # [PLANNED: delete] SUPERSEDED by bootstrap/config.py,
│                                 #   still the only settings module payperuse_consumer reads.
│                                 #   Its docstring records the deliberate disagreements.
├── bootstrap/                    # ALL reusable code lives here
│   ├── __init__.py               # public surface, re-exported LAZILY via PEP 562 __getattr__
│   ├── config.py                 # shared settings (Kafka / Postgres / Redis) + build_consumer_config
│   ├── launcher.py               # argparse, name validation, --list, logging, importlib, asyncio.run
│   ├── lifecycle.py              # infra() ctx manager (DB + Redis), session_scope(), shutdown_event()
│   └── consumers.py              # ManagedConsumer(confluent_kafka.Consumer) + factories
├── [PLANNED] tests/               # UNTRACKED prototype on disk (`git status`: `?? tests/`) —
│                                 #   not part of this branch. Would be the pytest rootdir — §3.6
│   ├── pytest.ini                #   asyncio_mode=auto, testpaths=unit, --strict-markers
│   ├── conftest.py               #   unreachable connection defaults + settings-cache clearing
│   └── unit/bootstrap/           #   test_config, test_launcher, test_lifecycle, test_consumers
├── Dockerfile                    # ENTRYPOINT ["python", "main.py"]; no default CMD
├── .dockerignore                 # keeps .env / .venv / caches out of the image — see §9.
│                                 #   Matched by the repo-root .gitignore, so present but UNTRACKED
├── env.template
├── requirements.txt
├── README.md
├── ARCHITECTURE.md               # this file
└── consumers/
    ├── __init__.py               # EMPTY
    └── payperuse_consumer/
        ├── __init__.py           # EMPTY — no side-effect import
        ├── main.py               # GROUP_ID + TOPIC + run() + loop
        │                         #   [PLANNED] the fence and the retry ladder (§6.4, §7.1)
        ├── handler.py            # handle_ppu_usage(msg) — no decorator
        ├── _billing.py
        └── [PLANNED] config.py   # PPU-only settings + Constants; still on the root config.py
```

**Deleted on this branch:** `consumers/registry.py` (`TOPIC_REGISTRY`,
`kafka_listener`, `KafkaRegistry`). `db_registry.py` went earlier; its shape is
what §3.3's named-connection registry reintroduces.
**Not yet deleted:** the service-root `config.py`, blocked on §5.
**Moved, not copied:** shared settings and `build_consumer_config()` now exist in
*both* modules and **deliberately differ** — see the §3.1 divergence table.
**In progress:** `tests/` and everything under it.

---

## 3. The `bootstrap/` package **`[SHIPPED]`**

> **The code in §3 is built**, at `services/kafka-consumers/bootstrap/`. **Its
> tests are not shipped** — a 75-case prototype exists locally at
> `tests/unit/bootstrap/` (§3.6), but it is untracked and must not be cited as
> committed coverage. The other thing not yet true is that `payperuse_consumer`
> imports none of it (§5) — so `bootstrap/config.py`'s settings and
> `build_consumer_config()` coexist with the superseded service-root `config.py`
> rather than having replaced it.

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

Everything that is infrastructure rather than domain, taken from the service-root
`config.py`. Settings are read through `@lru_cache` accessors
(`get_kafka_settings()`, `get_db_settings()`, `get_redis_settings()`) rather than
instantiated at import time, so merely importing the module cannot explode — which
is what makes §3.2's "the launcher imports no config" rule easy to keep, and is
also what a test suite would rely on to import `build_consumer_config` without a
full environment (§3.6 — no such suite is committed yet).
The substance is unchanged: settings are still read once, from the environment,
and still fail loudly — just at `run()` time, when logging is configured and the
consumer name is known.

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

> **`enable.auto.offset.store=False` was removed from this table.** It shipped
> here until a later edit dropped it from `build_consumer_config()` without
> updating this section. §6.1 explains why that key is load-bearing and what
> breaks without it — treat its absence as an open defect (see the banner at
> the top of this document), not as a corrected design.

| Key | Value | Why |
|---|---|---|
| `enable.auto.commit` | `False` | §6.1 |
| `partition.assignment.strategy` | `cooperative-sticky` | §6.5 |
| `error_cb` | `BrokerErrorReporter()` | Without one, `_TRANSPORT` / `_ALL_BROKERS_DOWN` never reach the application: the binding always registers a default that discards them. The consumer can then be disconnected indefinitely while `consume()` returns `[]`, the loop spins, and the Docker healthcheck sees a live process. **Rate-limited per error code**, one line per code per 60s — measured against an unreachable broker librdkafka fires 32 callbacks in ~1.5s, *alternating* `_TRANSPORT` and `_ALL_BROKERS_DOWN`, so deduping on "the last code" would suppress nothing. It runs on librdkafka's own thread, hence `time.monotonic()` and not `loop.time()`. |
| `logger=` (constructor kwarg, not config) | `logging.getLogger("librdkafka")` | Routes librdkafka's own output through `ai4i_core.logging`. Without it, `FAIL` lines go to raw stderr in librdkafka's `%3\|…\|FAIL\|` format — visible in `docker logs`, but not structured JSON and not parseable into OpenSearch. |

`KAFKA_ENABLE_AUTO_COMMIT` additionally carries a validator that **rejects
`true`** rather than silently ignoring a deployment that asked for auto-commit.

**`KAFKA_AUTO_OFFSET_RESET` should default to `error`, not `earliest` — but it no
longer does.** It shipped as `error` for one revision of this branch and was
reverted to `earliest` in a later edit, without a corresponding update here.
See §10: with `earliest`, an offset that ages out of retention causes a silent
full-topic replay and mass double-billing. `error` would turn that into an
`_AUTO_OFFSET_RESET` error entry — an alert and a human decision — and would
make a brand-new consumer group refuse to start until its offsets are seeded
(§10), which is the safety property this setting is meant to provide. As shipped
today, a brand-new group under `bootstrap/config.py` gets exactly the silent
replay §10.1 warns about, with no different behaviour from the root `config.py`.

> **The two settings modules mostly agree now, and that is a regression, not a
> convergence.** The table above describes `bootstrap/config.py`, which is what
> a new consumer gets. The service-root `config.py` — the only module
> `payperuse_consumer` imports — sets only `bootstrap.servers`, `group.id`,
> `auto.offset.reset`, `enable.auto.commit`, `session.timeout.ms` and
> `max.poll.interval.ms`. Of the three keys this document previously documented
> as differing, **only one still does**:
>
> | | root `config.py` | `bootstrap/config.py` |
> |---|---|---|
> | `KAFKA_AUTO_OFFSET_RESET` default | `earliest` | `earliest` — **no longer differs; was `error`, reverted without updating this doc** |
> | `enable.auto.offset.store` | not set (librdkafka default: `true`) | not set — **no longer differs; the `False` override was removed from `build_consumer_config()`** |
> | `partition.assignment.strategy` | not set (default: `range,roundrobin`) | `cooperative-sticky` |
> | `error_cb` / `logger=` | not set | set |
> | settings instantiation | at import time, as `settings` | lazily, via `@lru_cache` accessors |
> | `Topics`, `AUTH_SERVICE_URL`, `Constants` | present | absent by design |
>
> A local, untracked prototype at
> `tests/unit/bootstrap/test_config.py::TestDivergenceFromTheRootConfig` asserted
> the old three-key table and now **fails** against the current
> `bootstrap/config.py` (confirmed: `test_auto_offset_reset_defaults_to_error`,
> `test_correctness_keys_are_fixed_not_configurable[enable.auto.offset.store-False]`,
> `test_the_root_default_is_still_earliest`, and
> `test_the_divergence_is_exactly_the_three_documented_keys` all fail in
> `test_config.py` (24 of 28 there still pass), plus
> `test_consumers.py::TestBuildBulkMessageConsumer::test_applies_settings_defaults`
> for the same reason — **5 failures total across the 75-case prototype, all one
> root cause.** Since no suite is committed (§3.6), nothing caught this. The `range,roundrobin` row is still load-bearing for §10.2 — that part
> of the design is intact. The `earliest` row is **not** why §10.1's
> silent-replay exposure is live for the billing consumer anymore; it is why
> that exposure is live for **every** consumer built via `bootstrap/config.py`,
> since migrating no longer changes this default at all. Setting
> `KAFKA_AUTO_OFFSET_RESET=error` explicitly, per consumer's environment, is
> now the only way to get the protection §10.1 describes.

`Topics` and `AUTH_SERVICE_URL` do **not** live here — they are per-consumer
(§5). A consumer that does not talk to auth-service must be able to boot without
`AUTH_SERVICE_URL` set. This is why the root `config.py` cannot simply be
deleted: those three names have nowhere to go until `payperuse_consumer` grows
its own `config.py`.

### 3.2 `bootstrap/launcher.py`

The whole launcher, so the root `main.py` is three lines. Responsibilities, in
order:

1. **Parse arguments.** `argparse` with `--consumer` and `--list` in a single
   `add_mutually_exclusive_group(required=True)` — the *group* is required, so
   exactly one of the two must be given. There is **no environment-variable
   fallback and no default** for `--consumer`.
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
    global _default_factory
    if name is None:
        if _default_factory is None:            # built lazily, cached, once
            _default_factory = async_sessionmaker(
                get_engine(), class_=AsyncSession, expire_on_commit=False
            )
        factory = _default_factory
    else:
        factory = _session_factories[name]      # KeyError -> RuntimeError naming what IS open
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

The default factory is built once from `get_engine()` — `init_database` creates
the engine, `get_engine()` hands it over — so this still initialises through
`ai4i_core.bootstrap`. `infra()` resets `_default_factory` to `None` on the way
out, so a second `infra()` in the same process rebinds rather than reusing a
factory over a disposed engine. Committing remains the caller's job in both
cases.

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
        # config + logger= are the ONLY things the C type sees; logger= is a
        # genuine base kwarg, not a custom one being forwarded.
        super().__init__(config, logger=_rdkafka_logger)
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
  `super().__init__(config, logger=...)`, then ordinary attribute assignment,
  then custom methods, with no `__new__` override needed. Pass the config dict as
  the sole **positional** argument and set everything else afterwards. `logger=`
  may accompany it because it is a genuine kwarg of the base type; do not try to
  forward *custom* keyword arguments through.
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

#### Also on the public surface

Three members the sketch above elides, all part of the contract:

- **`generation -> int`** — a counter bumped on every assign and every drop. A
  consumer that caches anything derived from its assignment can compare it before
  and after an `await` to detect that a rebalance happened in between, without
  inspecting the partition set itself.
- **`add_revocation_hook(hook: RevocationHook)`** — registers a callback invoked
  with the revoked `set[(topic, partition)]` on both revoke and loss. A consumer
  holding *per-partition* state (a retry counter, a buffer) **must** drop it here:
  stale state for a partition you no longer own would suppress processing if that
  partition came back (§6.5). Hooks run on the executor thread inside
  `consume()`, and an exception in one is caught and logged rather than allowed to
  wedge the rebalance. The §5 reference shape retries the in-hand `Message` and
  holds no per-partition state, so it registers nothing — which is why the
  mechanism is easy to miss.
- **`RevocationHook`** — the type alias, `Callable[[set[tuple[str, int]]], None]`.

`commit_stored()` also swallows one more error than §3.4 describes:
`KafkaError._ASSIGNMENT_LOST`, logged at `ERROR` as *"Commit rejected —
assignment lost mid-message; this message will be redelivered to its new
owner"*. The side effect already landed and the new owner will redo it, so
crashing changes nothing. This is why §6.4's note about commits "beginning to
fail with `_ASSIGNMENT_LOST`" no longer takes the process down.

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
enforced by shared code, so the invariants below are **normative** and a loop that
violates them is a bug regardless of whether it appears to work.

**There is no reference implementation to copy today.** The §5 `run()` sketch is
the normative shape; `consumers/payperuse_consumer/main.py` is *not* it — that
loop predates `bootstrap/`, uses none of `ManagedConsumer`, and knowingly departs
from §6.1/§6.8 (see the §6 banner). What is worth taking from it is its
**comments**, each of which records a production failure that was actually hit —
the 8-partition per-partition-offset bug in particular. If a second consumer ends
up with a byte-identical loop, that is the signal to promote the loop into
`bootstrap/` — not a reason to have done so preemptively.

### 3.6 Tests for the shared code **`[PLANNED]`** 

> **There is no test suite on this branch.** `bootstrap/` (§3) ships with zero
> committed tests. It is documented here because it is
> a working draft of what §3.6 asks for, and the target design and layout it
> demonstrates are worth recording before it lands.
>
> **Not `bootstrap/tests/`.** Both the original design and the prototype put
> tests under a service-level `tests/` directory rather than beside the code
> they cover — test code, `conftest.py` and `pytest.ini` all under
> `services/kafka-consumers/tests/`, making `tests/` the pytest **rootdir** once
> finalized. The intended invocation:
>
> ```bash
> python -m pytest tests/unit          # from the service root
> cd tests && python -m pytest         # equivalent
> ```
>
> A bare `pytest` from the service root would find no config, get no
> `asyncio_mode` and no `testpaths`, and would try to collect `.venv`.
>
> **Also unresolved:** `pytest` and `pytest-asyncio` (required — the prototype's
> `pytest.ini` sets `asyncio_mode = auto`) are declared nowhere. `requirements.txt`
> is runtime-only.

The prototype carries unit tests for the shared code, none needing a broker, a database or Redis. `conftest.py` sets every
connection variable to a deliberately unreachable value, so a code path that
tries to reach real infrastructure would fail loudly rather than quietly
succeeding against whatever is running on the developer's machine. It also clears
the `@lru_cache` settings accessors between tests, without which every
`monkeypatch.setenv` case would be order-coupled.

**What the prototype currently asserts, file by file** — a starting point for
whoever commits it, not a claim of present coverage:

| File | What it asserts |
|---|---|
| `test_launcher.py` | Name validation accepts valid names and rejects dotted paths, traversal, uppercase, hyphens, the empty string and leading digits; unknown names exit `2`; a rejected name is **never imported**; `--list` enumerates the `consumers/` directory; no arguments is a usage error; `--consumer` and `--list` are mutually exclusive; a missing or non-callable `run` exits `2`; `KeyboardInterrupt` is a clean exit; importing the launcher pulls in no config and needs no environment; the root entrypoint is a thin delegate |
| `test_config.py` | `KAFKA_BATCH_SIZE` defaults to `1` and rejects `0`; asking for auto-commit fails loudly; the broker address is required; the group id is **not** a setting; importing the module reads no settings and each accessor reads once; `build_consumer_config` takes `group_id` as a parameter and maps settings onto librdkafka keys; `KAFKA_POLL_TIMEOUT_S`/`KAFKA_BATCH_SIZE` are *not* librdkafka keys; `BrokerErrorReporter` rate-limits per code rather than globally and logs `CRITICAL` for a fatal error. **Stale as of the latest `bootstrap/config.py` edit — 4 of 28 cases in this file now fail:** it still asserts `KAFKA_AUTO_OFFSET_RESET` defaults to `error`, that `enable.auto.offset.store` is a fixed correctness key, and that the divergence from the root `config.py` is exactly three keys. All three are false against the current code (§3.1, §10.1) |
| `test_lifecycle.py` | The named-connection registry: `add_database` opens by `db_name` or by `url`, is idempotent, and rejects both-or-neither; `get_engine_for` raises for an unopened name and says what *is* open; closing one leaves the others; closing an absent name is a no-op; `close_all_databases` disposes everything; `session_scope` yields a session, leaves committing to the caller, rolls back **and re-raises** on error, and builds the default factory once from the shared engine; `shutdown_event()` registers a handler for each signal and is set by both `SIGTERM` and `SIGINT` |
| `test_consumers.py` | The §3.4 subclass caveats, one test each: `ManagedConsumer` can actually be constructed on top of the C extension type, no wrapper name shadows an inherited one, and the wrappers delegate to inherited names that do exist. Plus `build_bulk_message_consumer` applying settings defaults, explicit arguments winning over settings, subscribing to the topic with **all three** rebalance callbacks, and starting with no assignment. **`test_applies_settings_defaults` also fails now** — same root cause as `test_config.py` below: it asserts `consumer.auto_offset_reset == "error"`, which is `"earliest"` against the current `bootstrap/config.py` |

The §3.4 caveats are worth a test each because both fail loudly in a test and
silently in production — that reasoning holds regardless of whether the suite
that implements it has landed.

**What is not covered, committed or otherwise:** `consumers/payperuse_consumer/`
— the billing SQL, the dedup semantics, the pricing resolution, the
auth-service notification and the loop's per-partition offset tracking are all
unasserted, including the two live defects in §7.1 and §7.3, which a loop-policy
test would have caught. Those tests belong at
`tests/unit/consumers/payperuse_consumer/` (§5) and are the largest gap in this
service once the shared-code suite itself is no longer the largest gap.
`infra()` is likewise untested even in the prototype; its two callees are
exercised only through the named-connection paths.

---

## 4. The launcher (`main.py`) **`[SHIPPED]`**

The root `main.py` is a three-line delegation; the launcher itself lives in
`bootstrap/launcher.py` and owns the responsibilities listed in §3.2. Splitting
it that way is what makes the logic testable without spawning a process — the
untracked `tests/unit/bootstrap/test_launcher.py` prototype (§3.6) asserts both
halves, though no committed suite does yet.

```python
# main.py — all of it
from bootstrap.launcher import main

if __name__ == "__main__":
    main()
```

```python
# bootstrap/launcher.py
CONSUMERS_DIR = Path(__file__).resolve().parent.parent / "consumers"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

def available_consumers() -> list[str]:
    """Directories under consumers/ that hold a main.py and have a legal name."""
    ...

def main(argv: list[str] | None = None) -> None:
    # --consumer / --list, mutually exclusive and required
    # regex AND allow-list validation before importlib.import_module()
    # configure_logging(service_name=f"kafka-consumer-{name}")
    # asyncio.run(run())
    ...
```

Note `parent.parent`: the module sits one level deeper than the file it replaced,
and `available_consumers()` is the single enumeration behind `--list`, the error
message **and** the allow-list check, so the three cannot drift apart.

Two invariants the file enforces and comments in place:

- **It imports no config** — neither `bootstrap.config` nor a consumer's.
  Pydantic settings read the environment at construction, so a launcher that
  imported shared or foreign config would let consumer A's missing variable break
  consumer B's process. Config is imported by the consumer module, after its name
  is known. This is also why `bootstrap/__init__.py` re-exports **lazily**, via
  PEP 562 `__getattr__`: eager re-exports would mean `import bootstrap.launcher`
  executes `bootstrap/__init__.py` and therefore imports `bootstrap.config`,
  breaking the rule through the package's front door. It additionally keeps
  `--list` and the argument-validation error paths working in an environment where
  sqlalchemy or the broker client cannot even be imported.
- **`--consumer` is validated by regex *and* allow-list** before reaching
  `importlib.import_module()`. An unvalidated value (`"../../something"`, or any
  dotted path) is arbitrary module import inside the container. Neither check
  may be relaxed to accept dotted paths.

Exit codes: `0` on clean shutdown after SIGTERM/SIGINT; `2` for an unknown or
malformed `--consumer` or a module with no callable `run`; non-zero for a
startup failure (database, Redis, broker), which the orchestrator restarts.

---

## 5. The consumer contract

> **Partly shipped.** `GROUP_ID` and `async def run()` are real and enforced —
> the launcher exits `2` if `run` is missing or not callable, and logs
> `GROUP_ID` at startup. The rest is `[PLANNED]` **for the one consumer that
> exists**: `payperuse_consumer.run()` is assembled from `ai4i_core.bootstrap`
> (`init_database`, `init_redis`, `close_database`) and the service-root
> `config.py` directly, **not** from the local `bootstrap/` package, and it has
> no `config.py` and no tests of its own. Everything it would need is built
> (§3) — migrating it is the outstanding work, and doing so is what finally
> allows the root `config.py` to be deleted.

Every `consumers/<name>/main.py` **must** expose:

- **`GROUP_ID: str`** — a hardcoded module constant. Never read from settings,
  never overridable by environment.
- **`async def run() -> None`** — the lifecycle, assembled from `bootstrap/`.

Its own `config.py` holds anything specific to it — its topic, service URLs, and
domain constants. Nothing consumer-specific goes in `bootstrap/config.py`.

### Optional: `rollback` — the escape hatch, not the mechanism

A consumer **may** expose `async def rollback(msg) -> None`, called when a
side effect must be compensated because the message should not have been
processed. **`payperuse_consumer` does not implement it, and should not.**


`rollback` exists for the case the conditional write cannot cover: a consumer
whose non-idempotent side effects reach **outside the database** — a payment
gateway, an email send, a third-party API — where there is no shared transaction
to gate on. That is a Saga-style compensation, and it is appropriate only when
atomicity is genuinely unavailable. A consumer that implements `rollback` must
document in its module docstring which effect is being compensated and what
happens if the compensation itself fails.

### Its own tests

A consumer without tests is not complete.
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
`tests/conftest.py` already sets every connection variable to an unreachable
value, so a consumer suite inherits that safety property for free.

### Shape of `run()` **for `payperuse_consumer`**

Every primitive below is built (§3). This is the shape a new consumer should have,
and the shape `payperuse_consumer` should be migrated to; it is **not** what that
consumer looks like today — see the §6 banner for the loop it actually runs.

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

> ### ⚠️ The shipped `payperuse_consumer` loop departs from §6.1 and §6.8
>
> **This banner is about that one consumer, not about `bootstrap/`.**
> `ManagedConsumer` provides everything §6 asks for — batch fetch via
> `consume_batch()`, the `owns()` fence, `store_processed()` / `commit_stored()`,
> and the rebalance callbacks behind them (§3.4). `payperuse_consumer` uses none
> of it: it builds a plain `confluent_kafka.Consumer`, calls single-message
> `poll()`, and has no fence at all — the assignment state `owns()` reads only
> exists on `ManagedConsumer`. A single-message `poll()` makes the in-flight
> window of §6.4 one message wide rather than zero.
>
> It also **batches its commits**:
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
> **§6.2 is only satisfied for the message itself, not for the partition.** An
> offset enters `pending_offsets` only after `handle_ppu_usage(msg)` returns
> successfully, and a failed message `continue`s without recording its own offset —
> so far so good. But `pending_offsets` is a per-partition high-water mark, so the
> next *successful* message on that partition overwrites the entry and the commit
> advances **past** the failed one. The net effect is that a failed message is
> silently dropped rather than retried. §7.1 has the detail; it is the most
> consequential divergence on this list and the one the loop's own comments get
> wrong.

### 6.1 Fetch in bulk, commit per message

**Bulk applies to the fetch, not to the commit.**

The failure that decides this: fetch 10 messages, process 5, crash before
committing. Those 5 are uncommitted, so on restart all 10 are redelivered and the
5 completed ones are processed a second time. For a billing consumer that means 5
spans re-billed — and the only thing standing in the way is a Redis key with a
1-hour TTL on an LRU instance. Any commit window wider than one message
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

**Two config keys must be false for this to hold.** Only one of them is:

| Key | Why false | Actually false in `bootstrap/config.py`? |
|---|---|---|
| `enable.auto.commit` | Nothing is committed on a timer behind your back. | Yes. |
| `enable.auto.offset.store` | **The important one.** Left at its default (`true`), a fetch marks a message's offset committable the instant it is returned — *including* messages whose processing later raised. Any commit would then advance past a failed message. | **No, as of the most recent edit to `build_consumer_config()`.** The key was removed entirely, so it is back at librdkafka's default (`true`). |

> ### ⚠️ This section's own guarantee does not hold for the shipped code
>
> `ManagedConsumer.build_bulk_message_consumer()` (§3.4) is tagged `[SHIPPED]`
> and is described throughout §6 as satisfying per-message-commit correctness.
> It does not, as of the config change above: `store_processed()` still calls
> `store_offsets()`, but that call is now redundant with an auto-store that
> already happened at fetch time. A consumer built exactly to the §5 shape,
> using nothing but shipped `bootstrap/` code, inherits the identical
> "commits past a failed message" defect documented for `payperuse_consumer` in
> §7.1 — the one difference is that `payperuse_consumer` never used this config
> path in the first place, so it was never protected by this key either way.
> Restoring `"enable.auto.offset.store": False` in `build_consumer_config()` is
> the fix; until then, do not treat `ManagedConsumer` as satisfying §6.1.

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

**The remaining guard would live at the sink**: gating the debit on the span key
not already being present, in the same SQL statement that performs it, so a
duplicate is *rejected by Postgres* rather than prevented by timing. That guard
is not implemented (§11) — it is a precondition for running more than one
replica, and the fence alone does not substitute for it.

Two consequences worth stating:

**This is why `KAFKA_BATCH_SIZE` defaults to `1`.** At a batch of one there is
nothing held when a revocation lands, so the fence is airtight and the window is
zero. It also sidesteps librdkafka's batch-API rebalance hazard entirely (§11),
which applies only above one.

The batch machinery is kept, not removed: `consume(num_messages=N)` is still the
call, `KAFKA_BATCH_SIZE` is still the knob, and raising it is a config change
rather than a rewrite. **One thing must be true before raising it:** the
write-time guard exists (§11), so a concurrent duplicate is rejected by
Postgres rather than merely narrowed by the fence.

Until it holds, a larger batch trades a real correctness margin for a fetch
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

| Outcome | Meaning | Offset                                                                                     |
|---|---|--------------------------------------------------------------------------------------------|
| **Success** | Handler returned | committed immediately (§6.1)                                                     |
| **Skip** | Message is not for us, or is permanently malformed | Recorded and committed — retrying cannot help                                              |
| **Failure** | Transient: infrastructure unavailable, unexpected error | **Not** recorded; the message is retried, but upon failure will move on to the next message |

### 7.1 A failed message must actually be retried

A message that fails must be retried , if still not succeeds then the next message should be processed  
 and the consumption continues. If the next message succeeds, the message is committed.

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

> **⚠️ Also a live defect, described here in the past tense until this pass.**
> `handler.py:57-61` still returns `None` from `_is_already_billed` on *any* Redis
> exception, and `handler.py:131-132`
> (`if is_already_billed or is_already_billed is None: return None`) still treats
> that identically to "already billed" — the span is dropped and its offset
> committed as a success. The `logger.warning` on the way out says "proceeding
> without dedup" and then does not proceed, which is why this reads as fixed when
> it is not. **Every Redis blip is unrecoverable revenue loss.** The table below
> is the target classification; the `Proceed` row is `[PLANNED]`.

The PPU handler returns `None` from its Redis dedup check on *any* Redis error,
and the caller treats that identically to "already billed": the event is dropped
**and** its offset committed.

Separate malformed input from infrastructure failure:

| Condition | Classification | Action |
|---|---|---|
| Empty dedup key (span has no `correlation_id`) | **Skip** | Skip permanently — retrying cannot help. Should warn; the shipped `_is_already_billed` returns `None` with **no log line at all**, so this skip is invisible. Unreachable in practice: `inference-service/trace/setup.py` already drops spans with no `correlation_id`. |
| Dedup key exists | **Skip** | Duplicate; already billed. |
| Dedup key absent | proceed | Bill. |
| Redis error during the dedup check | **Proceed** | Warn and bill. The write-time guard would be the authority; Redis is only the fast path. |
| Postgres error during the billing write | **Failure** | Raise. Retried by §7.1. |

**The Redis row changes meaning once a write-time guard ships (§11), and it is
worth being explicit about why.** While Redis dedup is the *only* guard, an error
there has no good answer: proceed and risk double-billing, or fail and stall.
Once the debit is gated in SQL, the question dissolves — a duplicate that slips
past a Redis outage is rejected by the guard, so the correct action is to warn
and carry on. Retrying would stall billing for the duration of a Redis incident
to protect against something Postgres already prevents.

Until that guard lands, treat a Redis error as a **Failure** instead: with no
authoritative guard behind it, retrying is the lesser risk. This is the one place
in §7 whose classification depends on whether the guard has shipped.

The general rule is unchanged: an error reaching *the store that owns the truth*
is a failure. Once the guard ships, that store is Postgres, not Redis.

### 7.4 Delivery guarantee

At-least-once. Three separate mechanisms bound three separate exposures, and it
matters which covers what:

| Exposure | Bounded by | To |
|---|---|---|
| **Crash** — process dies after a side effect, before its commit | Per-message commit (§6.1) | One message |
| **Rebalance** — partition reassigned while its messages are held | The `owns()` fence (§6.4) | One message: the one in flight when the revocation landed |
| **Concurrency** — old and new owner both believe they hold the partition | **Nothing in Kafka.** Only a guard at the sink (not yet implemented, §11) | Rejected at write time, within the guard's `N`-key window |

The third row is the important one. The first two are *narrowing* mechanisms —
they shrink windows, they do not close them, and no commit strategy can, because
during a rebalance the losing consumer has not yet learned it lost. Handlers must
therefore be idempotent regardless of how tight the first two are.

Note the third row's bound is not "zero" either: the planned guard is a bounded
set, not a unique constraint, so a duplicate arriving after `N` other billings
for the same tenant would not be rejected.

The PPU handler's Redis dedup key — a 1-hour cache entry on an LRU instance — is
adequate as a fast path against the one-message windows, and **not** adequate as
the guard against concurrent processing (§11).

---

## 8. Running multiple replicas — gated on the write-time guard

Multiple deployments per consumer are expected. Kafka handles the mechanics: each
consumer has its own group id, and the coordinator spreads partitions across
whatever members are alive. What Kafka does **not** handle is two members briefly
processing the same offsets during a rebalance (§6.4) — which on a billing path
means charging a customer twice.

> **Replicas stay at `1` until the write-time guard and the reconciliation job
> that backstops it are live (§11). Once both ship, replicas may be raised.**
> A hard gate, not a preference. Everything below is what makes lifting it safe.

### 8.1 What to expect operationally

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
wrong. **This is why `KAFKA_AUTO_OFFSET_RESET` *should* default to `error`** —
the reset becomes an alert and a human decision instead of a silent mass
re-bill. `bootstrap/config.py` shipped that default for one revision of this
branch; a later edit reverted it to `earliest` (§3.1).

> **Not shipped anywhere today.** Both `config.py` and `bootstrap/config.py`
> default `KAFKA_AUTO_OFFSET_RESET` to `earliest`, so **every consumer is
> currently exposed to exactly the silent replay described above** —
> `payperuse_consumer`, and any new consumer built via `bootstrap/config.py`
> that does not explicitly override the variable in its own environment.
> Migrating `payperuse_consumer` onto `bootstrap/config.py` (§5) no longer
> changes this; it only picks up `cooperative-sticky`, which is why the
> group-id sequencing in §10.2 is still required for that reason alone. Setting
> `error` deliberately, per consumer, is not a safe drive-by change on an
> **existing** group: it stops that consumer starting until its offsets are
> re-seeded (§10.2's runbook). For a **new** consumer with no prior offsets,
> there is no such cost — set it from day one.

### 10.2 Why `payperuse_consumer` keeps the legacy group id

**`[SHIPPED]` — `GROUP_ID = "aio-python-consumers"`, unchanged and deliberately so.**

The group already holds committed offsets for the topic, and the
`KAFKA_AUTO_OFFSET_RESET` this consumer reads is `earliest`. Renaming it would
give the new group no committed offsets, and `earliest` would then replay the
whole topic from the beginning and **re-bill every span still in retention**. The
dedup TTL is one hour, so anything older than that is billed a second time.

Keeping the id is safe today because the shipped consumer does not change the
assignment strategy: the **service-root** `build_consumer_config()` sets no
`partition.assignment.strategy`, so this process uses the same librdkafka
default (`range,roundrobin`) the old one did. There is no assignor mismatch and
a rolling restart rebalances normally. This is the one place where
`payperuse_consumer` still reading the superseded config module is load-bearing
rather than merely unfinished — `bootstrap/config.py` *does* set
`cooperative-sticky`, so migrating the consumer (§5) and keeping the group id are
mutually exclusive.

Renaming the group is therefore an **operational change, not a code change**,
and it becomes necessary exactly when this consumer moves onto
`bootstrap/config.py` and picks up `cooperative-sticky` — at that point the old
and new processes share no common assignor and a group cannot form. Sequence it
as: seed the new group's offsets from the old one *before* its first start, with
the old consumer stopped.

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

Recorded deliberately. None are addressed by this redesign.

- **A Redis outage drops spans instead of billing them** (§7.3).
  `_is_already_billed` returns `None` on any Redis exception and the caller treats
  `None` as "already billed", so the span is skipped and its offset committed —
  while logging "proceeding without dedup". **This loses revenue for the duration
  of any Redis incident.** The intended behaviour is to warn and bill, which is
  safe once a write-time guard exists.
- **Duplicate-billing window** between `db.commit()` and the Redis dedup `set`.
  Would be closed by a write-time guard at the sink (not yet implemented); live
  until it ships, which is what the §8 replica gate exists for.
- **Loop logic is copied, not shared** (§3.5) — a deliberate line, but a real
  cost: the offset and retry discipline of §6 and §7 is normative and unenforced.
  Watch for the second consumer; a byte-identical loop is the signal to promote it
  into `bootstrap/`.
- **Log context is empty.** `ContextFilter` injects `trace_id` / `tenant_id` from
  contextvars, but nothing in this process sets them (`RequestMiddleware` is
  FastAPI-only), so every line carries null trace context and the formatter
  generates a fresh `trace_id` per line. Setting `trace_id` per message from the
  span's `correlation_id` would make consumer logs correlate with inference logs.

---

## 12. Adding a new consumer **`[SHIPPED]`**

> **This procedure works as written.** `bootstrap/config.py`,
> `ManagedConsumer.build_bulk_message_consumer` and `infra()` all exist. The same
> steps, with a worked code sketch, are in *Adding a consumer* in
> [README.md](./README.md).
>
> **Do not copy `payperuse_consumer` wholesale.** It predates `bootstrap/` and is
> not the shape below — it imports the superseded root `config.py`, builds a plain
> `Consumer`, and runs a single-message loop with batched commits (see the §6
> banner). Copy its loop *comments* and its offset discipline; take its imports and
> its consumer construction from here instead.

1. Create `consumers/<name>_consumer/` with an **empty** `__init__.py`.
2. Add `config.py` for that consumer's topic and any service URLs. Nothing goes
   into `bootstrap/config.py`.
3. Add the handler — a plain async function taking a `confluent_kafka.Message`.
   No decorator, no registration.
4. Add `main.py` with a hardcoded `GROUP_ID` and `async def run()`. Build the
   consumer with `ManagedConsumer.build_bulk_message_consumer(...)`, wrap the
   lifecycle in `infra()`, and write the loop to the shape in §5 — honouring every
   invariant in §6 and §7.
5. Add tests at `tests/unit/consumers/<name>_consumer/`, covering the handler, the
   config, and the loop policy you just wrote (§5). The loop is the part no shared
   code enforces — test it here or nothing does. **Note that `tests/` itself is
   not yet a committed part of this repo** (§3.6, `[PLANNED]`) — landing it is a
   prerequisite, not an assumption you can skip past.
6. **Set `KAFKA_AUTO_OFFSET_RESET=error` for this consumer yourself, then seed
   its offsets before first start** (§10). `bootstrap/config.py` does **not**
   default this to `error` — as shipped it defaults to `earliest`, same as the
   root `config.py`, so a brand-new group silently replays the whole topic
   unless you override it. There is no free protection here: this is a step you
   must take, not a default you can rely on. Give the new consumer its own
   environment for the variable — `KAFKA_AUTO_OFFSET_RESET` is a single
   process-level setting, so if the deployment's shared `.env` sets it to
   `earliest` for `payperuse_consumer`'s sake, a new consumer sharing that file
   inherits `earliest` too.
7. Add a deployment unit running the shared image with
   `--consumer <name>_consumer`.

There is no root `main.py` to edit and no registry to update. If
`consumers/<name>/main.py` exists with a callable `run`, the launcher can run it.

If step 4 produces a loop identical to another consumer's, promote it into
`bootstrap/` and have both call it.
