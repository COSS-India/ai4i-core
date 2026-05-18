# `ai4icore_logging` — Usage Analysis

**Status:** Factual map of who imports the lib (direct and transitive) and who doesn't.
**Generated:** 2026-05-15

> Scope note: this doc covers the standalone `libs/ai4icore_logging/` path.
> A consolidated mirror exists at
> `libs/ai4icore_core/ai4icore_core/logging/`, but no service or other lib
> imports from `ai4icore_core.logging` today — every consumer in the repo
> uses the `ai4icore_logging` path.

---

## TL;DR

`ai4icore_logging` provides the platform's **structured JSON logging
stack**: a configured `get_logger()`, a Kafka-shipping handler for log
aggregation, a JSON formatter, trace/organization/tenant ContextVars,
and FastAPI middleware that stamps each request with a correlation/trace
ID. It also exposes a `LoggingPlugin` that wires all of this into a
FastAPI app in one call (`register_logging_plugin(app)`).

**Direct consumers in `services/`:** 7 services import the lib across 13
Python files.

```
alert-management-service (4),  smr-service (3),  pipeline-service (2),
auth-service (1),  platform-core-service (1),  policy-service (1),
alert-config-sync-service (1)
```

**Indirect consumers via other shared libs** — services pull the lib in
transitively whenever they consume any of these:

```
ai4icore_bootstrap.factory                 → get_logger, configure_logging, RequestLoggingMiddleware
ai4icore_service_base.app_factory          → LoggingConfig, get_logger, register_logging_plugin
ai4icore_observability.middleware          → ai4icore_logging.context (set_organization, set_tenant_id, get_tenant_id)
ai4icore_telemetry.tracing                 → ai4icore_logging.context (get_organization, get_tenant_id)
```

That means **all 11 inference services + `pipeline-service`** that call
into `ai4icore_service_base` end up with `ai4icore_logging` in their
dependency graph even when they don't import it directly. The same is
true for any service that registers `ai4icore_observability`.

**Services with zero footprint** (no Python import, no Dockerfile
install, no compose mount): `api-gateway-service` / `api-gateway-legacy`
(nginx-only), `auth-service-v2` (decommissioned), `docs-manager`,
`model-management-service`, `multi-tenant-feature`, `pay-per-use-service`,
`policy-engine`, `request-profiler`, `alerting-service`,
`dashboard-service`, `config-service`, `metrics-service`,
`telemetry-service`. Most of these are background workers, gateway
processes, or services that use Python's stdlib `logging` directly.

---

## 1. What the lib provides

Source: [libs/ai4icore_logging/ai4icore_logging/](../libs/ai4icore_logging/ai4icore_logging/)

| Module | LOC | Public surface | Purpose |
|---|---:|---|---|
| `logger.py` | 182 | `get_logger(name)`, `configure_logging(...)` | The entry point: returns a logger pre-wired with the JSON formatter, Kafka handler, and trace context. |
| `middleware.py` | 360 | `CorrelationMiddleware`, `RequestLoggingMiddleware`, `get_correlation_id`, `get_trace_id_from_request` | FastAPI middleware that stamps each request with a correlation/trace ID, sets it on `request.state`, and emits a structured `request_completed` log line. |
| `service_request_logging.py` | 297 | `ServiceRequestLoggingMiddleware` | Variant middleware for service-to-service request logging. |
| `formatters.py` | 236 | `JSONFormatter` | Renders log records to JSON, including trace/organization/tenant context fields. |
| `plugin.py` | 147 | `LoggingPlugin`, `create_logging_plugin`, `register_logging_plugin(app)` | One-call wiring helper. |
| `context.py` | 140 | `TraceContext`, `set_trace_id`/`get_trace_id`/`clear_trace_id`, `set_organization`/`get_organization`/`clear_organization`, `generate_trace_id` | ContextVar-based propagation of trace IDs, organization name, and tenant ID across async boundaries. |
| `config.py` | 124 | `LoggingConfig` (pydantic-settings) | Env-driven config (`LOG_LEVEL`, `KAFKA_*`, `USE_KAFKA_LOGGING`, etc.). |
| `handlers.py` | 115 | `KafkaHandler` | Async handler that ships structured logs to Kafka for downstream aggregation. |
| `__init__.py` | 60 | Re-exports the above | Single import surface. |
| **Total** | **1,661** | | |

Dependencies declared in [libs/ai4icore_logging/pyproject.toml](../libs/ai4icore_logging/pyproject.toml):

```
python-json-logger >= 2.0.7
kafka-python >= 2.0.2
aiokafka >= 0.8.0
```

`ai4icore_logging` also imports `ai4icore_env` internally
(`app_env.log_level`, `app_env.kafka_*`, `app_env.use_kafka_logging`,
`app_env.service_name`, …), so anything that pulls in
`ai4icore_logging` also pulls in `ai4icore_env`.

---

## 2. Who consumes it

### 2.1 Direct imports in services (Python source)

| Service | File | Symbols imported |
|---|---|---|
| `alert-management-service` | [`main.py:7`](../services/alert-management-service/main.py#L7) | `get_logger`, `LoggingConfig`, `register_logging_plugin` |
| `alert-management-service` | [`alert_management.py:29`](../services/alert-management-service/alert_management.py#L29) | `get_logger` |
| `alert-management-service` | [`routers/alert_history.py:10`](../services/alert-management-service/routers/alert_history.py#L10) | `get_logger` |
| `alert-management-service` | [`utils/audit_logger.py:14`](../services/alert-management-service/utils/audit_logger.py#L14) | `get_logger` |
| `smr-service` | [`main.py:25`](../services/smr-service/main.py#L25) | `get_logger` |
| `smr-service` | [`db_connection.py:6`](../services/smr-service/db_connection.py#L6) | `get_logger` |
| `smr-service` | [`db_operations.py:14`](../services/smr-service/db_operations.py#L14) | `get_logger` |
| `pipeline-service` | [`app/main.py:31`](../services/pipeline-service/app/main.py#L31) | `get_logger`, `LoggingConfig`, `register_logging_plugin` |
| `pipeline-service` | [`app/routes/pipeline.py:34`](../services/pipeline-service/app/routes/pipeline.py#L34) | `get_correlation_id` |
| `auth-service` | [`app/middleware/request_logging.py:9`](../services/auth-service/app/middleware/request_logging.py#L9) | `RequestLoggingMiddleware` |
| `platform-core-service` | [`app/middleware/request_logging.py:9`](../services/platform-core-service/app/middleware/request_logging.py#L9) | `RequestLoggingMiddleware` |
| `policy-service` | [`app/main.py:18`](../services/policy-service/app/main.py#L18) | `register_logging_plugin` |
| `alert-config-sync-service` | [`main.py:37`](../services/alert-config-sync-service/main.py#L37) | `get_logger`, `configure_logging` |

Total: **13 import lines across 13 files in 7 services.**

Two distinct usage patterns:

1. **Plugin-style integration** (alert-management, pipeline, policy):
   `register_logging_plugin(app)` wires the whole structured logging
   stack into the FastAPI app in one call.
2. **Direct logger / middleware usage** (everyone else): the service
   either calls `get_logger(__name__)` to get a JSON-emitting logger, or
   adds `RequestLoggingMiddleware` to its FastAPI app to stamp
   trace/correlation IDs on requests.

### 2.2 Indirect — via four other shared libs

Four other libs in `libs/` import `ai4icore_logging`:

| Consumer lib | File | Symbols | When it loads |
|---|---|---|---|
| `ai4icore_bootstrap` | [factory.py:112](../libs/ai4icore_bootstrap/ai4icore_bootstrap/factory.py#L112) | `get_logger`, `configure_logging`, `RequestLoggingMiddleware` | Bootstrap factory wires structured logging into apps that use it. Falls back to stdlib logging via `try/except ImportError`. |
| `ai4icore_service_base` | [app_factory.py:70](../libs/ai4icore_service_base/ai4icore_service_base/app_factory.py#L70) | `LoggingConfig`, `get_logger`, `register_logging_plugin` | `create_inference_app(...)` registers the logging plugin. All 11 inference services + `pipeline-service` use this factory transitively. |
| `ai4icore_observability` | [middleware.py:150](../libs/ai4icore_observability/ai4icore_observability/middleware.py#L150) | `ai4icore_logging.context.set_organization`, `set_tenant_id`, `get_tenant_id` | Observability middleware seeds the org/tenant ContextVars from JWT claims so they appear in subsequent log records. |
| `ai4icore_telemetry` | [tracing.py:134](../libs/ai4icore_telemetry/ai4icore_telemetry/tracing.py#L134) | `ai4icore_logging.context.get_organization`, `get_tenant_id` | Trace spans pick up org/tenant labels from the same ContextVars. |

Implication: a service that calls `create_inference_app(...)` (or
otherwise pulls in `ai4icore_service_base`) ends up with the full
logging stack registered even if its own code never says
`from ai4icore_logging import …`. Same for any service that registers
`ai4icore_observability` or `ai4icore_telemetry`.

### 2.3 Compose / Dockerfile bindings (operational, not code)

* **Dockerfile (build time):** **19 services** `COPY libs/ai4icore_logging` + `pip install -e .`:

  ```
  alert-config-sync-service, alert-management-service, asr-service,
  audio-lang-detection-service, auth-service, language-detection-service,
  language-diarization-service, llm-service, ner-service, nmt-service,
  ocr-service, pii-service, pipeline-service, platform-core-service,
  policy-service, smr-service, speaker-diarization-service,
  transliteration-service, tts-service
  ```

* **docker-compose-local.yml (dev hot-reload):** **17 service blocks**
  bind-mount `./libs/ai4icore_logging:/...`:

  ```
  alert-config-sync-service, alert-management-service, asr-service,
  audio-lang-detection-service, auth-service, language-detection-service,
  language-diarization-service, llm-service, ner-service, nmt-service,
  ocr-service, pipeline-service, platform-core-service, smr-service,
  speaker-diarization-service, transliteration-service, tts-service
  ```

Note: services like `asr-service`, `nmt-service`, `tts-service`, etc.
install + mount the lib but do **not** import it from their own code —
they pick it up transitively via `ai4icore_service_base.app_factory` (§2.2).

---

## 3. Who does **not** use it

Services with **zero** Python imports of `ai4icore_logging`:

| Service | Dockerfile installs? | Compose mounts? | How it logs (likely) |
|---|:---:|:---:|---|
| `asr-service` | ✓ | ✓ | Via `ai4icore_service_base.create_inference_app` (transitive). |
| `audio-lang-detection-service` | ✓ | ✓ | Same. |
| `language-detection-service` | ✓ | ✓ | Same. |
| `language-diarization-service` | ✓ | ✓ | Same. |
| `llm-service` | ✓ | ✓ | Same. |
| `ner-service` | ✓ | ✓ | Same. |
| `nmt-service` | ✓ | ✓ | Same. |
| `ocr-service` | ✓ | ✓ | Same. |
| `speaker-diarization-service` | ✓ | ✓ | Same. |
| `transliteration-service` | ✓ | ✓ | Same. |
| `tts-service` | ✓ | ✓ | Same. |
| `pii-service` | ✓ | ✗ | Installed via Dockerfile; not imported in code. |
| `alerting-service` | ✗ | ✗ | Stdlib logging. |
| `config-service` | ✗ | ✗ | Stdlib logging. |
| `dashboard-service` | ✗ | ✗ | Stdlib logging. |
| `docs-manager` | ✗ | ✗ | Static docs manager. |
| `metrics-service` | ✗ | ✗ | Stdlib logging. |
| `model-management-service` | ✗ | ✗ | Stdlib logging. |
| `multi-tenant-feature` | ✗ | ✗ | Legacy. |
| `pay-per-use-service` | ✗ | ✗ | |
| `policy-engine` | ✗ | ✗ | |
| `request-profiler` | ✗ | ✗ | |
| `telemetry-service` | ✗ | ✗ | Stdlib logging (it *consumes* logs into OpenSearch; doesn't emit through this lib). |
| `auth-service-v2` | ✗ | ✗ | Decommissioned. |
| `api-gateway-service` | ✗ | ✗ | nginx-only. |
| `api-gateway-legacy` | ✗ | ✗ | nginx-only. |

The big group at the top (the 11 inference services + `pii-service`)
all have the lib installed but **don't import it directly** — they get
the full logging stack wired up via the `ai4icore_service_base`
factory, so their own application code just uses stdlib `logging` (or
`get_logger(__name__)` indirectly through helpers).

**Reproducible verification:**

```bash
# Services importing ai4icore_logging in Python source
grep -rln "ai4icore_logging" services/ --include='*.py' | awk -F/ '{print $2}' | sort -u

# Libs importing ai4icore_logging (transitive consumers)
grep -rEln "^\s*(from|import)\s+ai4icore_logging" libs/ --include='*.py' | grep -v '/ai4icore_logging/'

# Compose blocks mounting it
awk '/^  [a-z][a-z0-9-]+:/{svc=$1} /libs\/ai4icore_logging\b/{print svc}' docker-compose-local.yml | sort -u

# Confirm nothing in the repo uses the consolidated mirror path
grep -rEn "^\s*(from|import)\s+ai4icore_core\.logging" services/ libs/ --include='*.py' \
  | grep -v '/ai4icore_core/ai4icore_core/'
```

---

## 4. What the lib depends on

```
python-json-logger >= 2.0.7
kafka-python >= 2.0.2
aiokafka >= 0.8.0
```

Plus an implicit runtime dependency on `ai4icore_env` (the lib reads
`app_env.log_level`, `app_env.kafka_*`, `app_env.use_kafka_logging`,
`app_env.service_name`).

---

## 5. Observations

1. **Most consumers reach the lib indirectly, not directly.** Only 7
   services import `ai4icore_logging` in their own code, but 11 inference
   services + `pipeline-service` (12 services total) get it wired up
   transitively via `ai4icore_service_base.create_inference_app`. So the
   effective consumer set is closer to ~18 services even though the
   direct-import count is 7.
2. **Two import surfaces.** The lib exposes both a high-level
   `register_logging_plugin(app)` (used by alert-management, pipeline,
   policy) and low-level primitives (`get_logger`, `RequestLoggingMiddleware`,
   `ai4icore_logging.context.*`) used by everyone else.
3. **`context.py` ContextVars are an implicit contract with other libs.**
   `ai4icore_observability.middleware` writes
   `set_organization` / `set_tenant_id` into these ContextVars, and
   `ai4icore_telemetry.tracing` reads `get_organization` / `get_tenant_id`
   from them. Renaming or moving those functions breaks observability
   labels and trace span attributes platform-wide.
4. **Defensive import pattern is common.** Multiple consumers wrap the
   `from ai4icore_logging import …` line in `try: … except ImportError`
   with a stdlib-logging fallback (e.g. [bootstrap/factory.py:112-125](../libs/ai4icore_bootstrap/ai4icore_bootstrap/factory.py#L112-L125),
   [smr-service/main.py:25](../services/smr-service/main.py#L25),
   [policy-service/app/main.py:18](../services/policy-service/app/main.py#L18)).
   The lib is treated as optional at the boundary even though every
   service ends up installing it.
5. **Inference services install the lib but don't import it.** The 11
   inference-service Dockerfiles + compose mounts pull
   `ai4icore_logging` into the image even though their own code never
   references it. The dependency is real (via the service-base factory);
   the installation is just operationalizing that real transitive dep
   into the image build.

---

## 6. Appendix — quick-reference grep results

```
$ git grep -lE "^\s*(from|import)\s+ai4icore_logging" \
    -- 'services/**.py' 'libs/**.py' ':!libs/ai4icore_logging/**'
libs/ai4icore_bootstrap/ai4icore_bootstrap/factory.py
libs/ai4icore_observability/ai4icore_observability/middleware.py
libs/ai4icore_service_base/ai4icore_service_base/app_factory.py
libs/ai4icore_telemetry/ai4icore_telemetry/tracing.py
services/alert-config-sync-service/main.py
services/alert-management-service/alert_management.py
services/alert-management-service/main.py
services/alert-management-service/routers/alert_history.py
services/alert-management-service/utils/audit_logger.py
services/auth-service/app/middleware/request_logging.py
services/pipeline-service/app/main.py
services/pipeline-service/app/routes/pipeline.py
services/platform-core-service/app/middleware/request_logging.py
services/policy-service/app/main.py
services/smr-service/db_connection.py
services/smr-service/db_operations.py
services/smr-service/main.py
```

13 service files across 7 services + 4 lib files (across 4 other shared libs).

```
$ git grep -lE "^\s*(from|import)\s+ai4icore_core\.logging" \
    -- 'services/**.py' 'libs/**.py' ':!libs/ai4icore_core/ai4icore_core/logging/**'
libs/ai4icore_core/ai4icore_core/bootstrap/factory.py        # internal mirror
libs/ai4icore_core/ai4icore_core/observability/middleware.py # internal mirror
libs/ai4icore_core/ai4icore_core/service_base/app_factory.py # internal mirror
libs/ai4icore_core/ai4icore_core/telemetry/tracing.py        # internal mirror
```

— no service-level matches for the consolidated mirror path.
