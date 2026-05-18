# `ai4icore_env` — Usage Analysis

**Status:** Factual map of who imports the lib (direct and transitive) and who doesn't.
**Generated:** 2026-05-15

> Scope note: this doc covers the standalone `libs/ai4icore_env/` path.
> A consolidated mirror exists at `libs/ai4icore_core/ai4icore_core/env/`,
> but no service or other lib imports from `ai4icore_core.env` today —
> every consumer in the repo uses the `ai4icore_env` path.

---

## TL;DR

`ai4icore_env` is the platform's **central environment-variable surface**
— a single `AppEnv` pydantic-settings class exposed as the singleton
`app_env`. Almost every service reads its runtime config (DB hosts, Redis
URLs, Kafka brokers, feature flags, etc.) by referencing
`app_env.<field>`.

**Direct consumers in `services/`:** 22 services import it across 41
Python files.

```
pipeline-service (5), nmt-service (5), config-service (4),
llm-service (3), asr-service (3), tts-service (2), telemetry-service (2),
smr-service (2), policy-service (2), language-diarization-service (2),
alert-management-service (2), transliteration-service (1),
speaker-diarization-service (1), pii-service (1), ocr-service (1),
ner-service (1), metrics-service (1), language-detection-service (1),
dashboard-service (1), audio-lang-detection-service (1),
alerting-service (1), alert-config-sync-service (1)
```

**Indirect consumers via other shared libs** — pulled in transitively
when a service imports any of these:

```
ai4icore_logging              (config, formatters, handlers, logger, middleware, service_request_logging)
ai4icore_telemetry            (config, jaeger_client, opensearch_client, tracing)
ai4icore_model_management     (client, config, triton_client)
ai4icore_observability        (config, dashboards)
ai4icore_service_base         (app_factory)
```

**Services with zero footprint** (no Python import, no Dockerfile
install, no compose mount): `api-gateway-service` / `api-gateway-legacy`
(nginx-only), `auth-service-v2` (decommissioned), `docs-manager`,
`model-management-service`, `multi-tenant-feature`, `pay-per-use-service`,
`policy-engine`, `request-profiler`.

Two notable cases where the lib is installed but the service's own code
doesn't import it directly: **`auth-service`** (defines its own
`AuthSettings(BaseSettings)` class and reads env vars locally, but its
docstring still references `ai4icore_env`) and **`platform-core-service`**
(installed + mounted, no direct import).

---

## 1. What the lib provides

Source: [libs/ai4icore_env/ai4icore_env/](../libs/ai4icore_env/ai4icore_env/)

| Module | LOC | Public surface | Purpose |
|---|---:|---|---|
| `settings.py` | 407 | `AppEnv` (pydantic-settings model) with ~120 fields covering service identity, DB, Redis, Kafka, OpenSearch/Elasticsearch, OpenTelemetry, model-management, observability, telemetry, JWT/auth, OAuth, email, rate limiting, etc. | The platform's canonical env-var schema. |
| `__init__.py` | 9 | `AppEnv`, `app_env` (singleton) | Single import surface. |
| **Total** | **416** | | |

Public API consumed by services is essentially two names:

```python
from ai4icore_env import app_env       # singleton (used everywhere)
from ai4icore_env import AppEnv        # the class (rarely used directly)
```

Almost all usage looks like `app_env.postgres_host`,
`app_env.redis_password`, `app_env.kafka_bootstrap_servers`, etc.

Dependencies declared in [libs/ai4icore_env/pyproject.toml](../libs/ai4icore_env/pyproject.toml):

```
pydantic >= 2.0.0
pydantic-settings >= 2.0.0
```

---

## 2. Who consumes it

### 2.1 Direct imports in services (Python source)

22 services import the lib across 41 files. The dominant pattern is a
per-service `app/core/config.py` (or `main.py`) that does:

```python
from ai4icore_env import app_env
# Re-export app_env for convenience — services use this for all config.
settings = app_env
```

…and everywhere else in the service references `settings.<field>` (or
`app_env.<field>` directly).

| Service | # files importing | Notes |
|---|:---:|---|
| `pipeline-service` | 5 | `app/main.py`, `app/core/config.py`, `app/clients/http_client.py`, `app/clients/service_registry_client.py`, `app/routes/pipeline.py` |
| `nmt-service` | 5 | `app/core/config.py`, `app/clients/model_management_client.py`, `app/services/smr_service.py`, `app/utils/try_it_utils.py`, `tests/test_triton_models.py` |
| `config-service` | 4 | `main.py`, `registry/zookeeper_client.py`, `routers/config_router.py`, `tests/conftest.py` |
| `llm-service` | 3 | `app/main.py`, `app/core/config.py`, `app/clients/triton_client.py` |
| `asr-service` | 3 | `app/core/config.py`, `app/services/smr_service.py`, `app/services/streaming_service.py` |
| `tts-service` | 2 | `app/core/config.py`, `app/services/smr_service.py` |
| `telemetry-service` | 2 | `main.py`, `routers/observability_router.py` |
| `smr-service` | 2 | `db_connection.py`, `main.py` |
| `policy-service` | 2 | `app/db/session.py`, `app/services/policy_service.py` |
| `language-diarization-service` | 2 | `app/core/config.py`, `app/main.py` |
| `alert-management-service` | 2 | `main.py`, `alert_management.py` |
| `transliteration-service` | 1 | `app/core/config.py` |
| `speaker-diarization-service` | 1 | `app/core/config.py` |
| `pii-service` | 1 | `main.py` |
| `ocr-service` | 1 | `app/core/config.py` |
| `ner-service` | 1 | `app/core/config.py` |
| `metrics-service` | 1 | `main.py` |
| `language-detection-service` | 1 | `app/core/config.py` |
| `dashboard-service` | 1 | `main.py` |
| `audio-lang-detection-service` | 1 | `app/core/config.py` |
| `alerting-service` | 1 | `main.py` |
| `alert-config-sync-service` | 1 | `main.py` |

### 2.2 Indirect — via five other shared libs

Five other libs in `libs/` import `ai4icore_env`, meaning services that
consume any of them transitively pick up `app_env`:

| Consumer lib | Files importing |
|---|---|
| `ai4icore_logging` | `config.py`, `formatters.py`, `handlers.py`, `logger.py`, `middleware.py`, `service_request_logging.py` |
| `ai4icore_telemetry` | `config.py`, `jaeger_client.py`, `opensearch_client.py`, `tracing.py` |
| `ai4icore_model_management` | `client.py`, `config.py`, `triton_client.py` (+ `tests/test_inference_ssl_verify.py`) |
| `ai4icore_observability` | `config.py`, `dashboards.py` |
| `ai4icore_service_base` | `app_factory.py` |

Practical implication: **any service that uses `ai4icore_service_base`
(all 11 inference services + `pipeline-service`), any service that wires
in `ai4icore_logging`, or any service that registers
`ai4icore_observability` / `ai4icore_telemetry`, ends up depending on
`ai4icore_env` transitively** — even if it never imports `ai4icore_env`
in its own code.

### 2.3 Compose / Dockerfile bindings (operational, not code)

* **Dockerfile (build time):** **24 services** `COPY libs/ai4icore_env` +
  `pip install -e .`:

  ```
  alert-config-sync-service, alert-management-service, alerting-service,
  asr-service, audio-lang-detection-service, auth-service, config-service,
  dashboard-service, language-detection-service, language-diarization-service,
  llm-service, metrics-service, ner-service, nmt-service, ocr-service,
  pii-service, pipeline-service, platform-core-service, policy-service,
  smr-service, speaker-diarization-service, telemetry-service,
  transliteration-service, tts-service
  ```

* **docker-compose-local.yml (dev hot-reload):** **22 service blocks**
  bind-mount `./libs/ai4icore_env:/...`:

  ```
  alert-config-sync-service, alert-management-service, alerting-service,
  asr-service, audio-lang-detection-service, auth-service, config-service,
  dashboard-service, language-detection-service, language-diarization-service,
  llm-service, metrics-service, ner-service, nmt-service, ocr-service,
  pipeline-service, platform-core-service, smr-service,
  speaker-diarization-service, telemetry-service, transliteration-service,
  tts-service
  ```

---

## 3. Who does **not** use it

Services with **zero** Python imports of `ai4icore_env`:

| Service | Dockerfile installs? | Compose mounts? | Notes |
|---|:---:|:---:|---|
| `auth-service` | ✓ | ✓ | Has its own `AuthSettings(BaseSettings)` in [app/core/config.py](../services/auth-service/app/core/config.py) — reads env vars locally via pydantic-settings, not via `app_env`. Docstring says "extends ai4icore_env" but the code doesn't import from it. |
| `platform-core-service` | ✓ | ✓ | Installed and mounted but no Python file imports `ai4icore_env`. Effectively dead infrastructure for this service. |
| `model-management-service` | ✗ | ✗ | Has its own settings layer. |
| `pay-per-use-service` | ✗ | ✗ | |
| `multi-tenant-feature` | ✗ | ✗ | |
| `policy-engine` | ✗ | ✗ | |
| `request-profiler` | ✗ | ✗ | |
| `docs-manager` | ✗ | ✗ | |
| `auth-service-v2` | ✗ | ✗ | Decommissioned. |
| `api-gateway-service` | ✗ | ✗ | nginx-only. |
| `api-gateway-legacy` | ✗ | ✗ | nginx-only. |
| `config-service`'s build helpers | n/a | n/a | The Python service `config-service` *does* import (already counted in §2.1); this row is just noting there's no separate non-Python piece. |

**Reproducible verification:**

```bash
# Services importing ai4icore_env in Python source
grep -rln "ai4icore_env" services/ --include='*.py' | awk -F/ '{print $2}' | sort -u

# Libs importing ai4icore_env (transitive consumers)
grep -rEln "^\s*(from|import)\s+ai4icore_env" libs/ --include='*.py' | grep -v '/ai4icore_env/'

# Compose blocks mounting it
awk '/^  [a-z][a-z0-9-]+:/{svc=$1} /libs\/ai4icore_env\b/{print svc}' docker-compose-local.yml | sort -u

# Confirm nothing in the repo uses the consolidated mirror path
grep -rEn "^\s*(from|import)\s+ai4icore_core\.env" services/ libs/ --include='*.py' \
  | grep -v '/ai4icore_core/ai4icore_core/'
```

---

## 4. What the lib depends on

```
pydantic >= 2.0.0
pydantic-settings >= 2.0.0
```

Both are baseline requirements for every FastAPI service in the
platform — `ai4icore_env` adds no new transitive weight.

---

## 5. Observations

1. **`ai4icore_env` is, by raw consumer count, one of the two most
   widely-used shared libs in the platform** (the other being
   `ai4icore_exceptions`). 22 services import it directly and a further
   5 shared libs depend on it transitively, so essentially every Python
   service in the repo touches it somehow.
2. **Two services have an inconsistent footprint** — they install/mount
   the lib but don't import it in their own code:
   * `auth-service` reads env vars through its own `AuthSettings`
     pydantic-settings class. The Dockerfile + compose mounts for
     `ai4icore_env` are inert for this service.
   * `platform-core-service` has the same inert installation pattern.
3. **`config-service`** *is* a consumer (4 files import `app_env`) even
   though it's logically the platform's config-distribution service —
   it reads its own bootstrap config (DB host, Zookeeper URL, etc.)
   from `app_env`.
4. **Public surface is tiny.** The `__init__.py` exports exactly two
   names (`AppEnv`, `app_env`), and ~99% of consumers use only the
   `app_env` singleton. The `AppEnv` class itself is rarely imported
   directly.
5. **The `app_env` singleton is constructed at import time.** Because
   the module instantiates `app_env = AppEnv()` when first loaded, any
   service that imports `ai4icore_env` (directly or transitively)
   triggers env-var validation at startup. Missing required env vars
   surface as a pydantic validation error at process start rather than
   at request time.

---

## 6. Appendix — quick-reference grep results

```
$ git grep -lE "^\s*(from|import)\s+ai4icore_env" \
    -- 'services/**.py' 'libs/**.py' ':!libs/ai4icore_env/**'
libs/ai4icore_logging/ai4icore_logging/config.py
libs/ai4icore_logging/ai4icore_logging/formatters.py
libs/ai4icore_logging/ai4icore_logging/handlers.py
libs/ai4icore_logging/ai4icore_logging/logger.py
libs/ai4icore_logging/ai4icore_logging/middleware.py
libs/ai4icore_logging/ai4icore_logging/service_request_logging.py
libs/ai4icore_model_management/ai4icore_model_management/client.py
libs/ai4icore_model_management/ai4icore_model_management/config.py
libs/ai4icore_model_management/ai4icore_model_management/triton_client.py
libs/ai4icore_model_management/tests/test_inference_ssl_verify.py
libs/ai4icore_observability/ai4icore_observability/config.py
libs/ai4icore_observability/ai4icore_observability/dashboards.py
libs/ai4icore_service_base/ai4icore_service_base/app_factory.py
libs/ai4icore_telemetry/ai4icore_telemetry/config.py
libs/ai4icore_telemetry/ai4icore_telemetry/jaeger_client.py
libs/ai4icore_telemetry/ai4icore_telemetry/opensearch_client.py
libs/ai4icore_telemetry/ai4icore_telemetry/tracing.py
services/alert-config-sync-service/main.py
services/alert-management-service/alert_management.py
services/alert-management-service/main.py
services/alerting-service/main.py
services/asr-service/app/core/config.py
services/asr-service/app/services/smr_service.py
services/asr-service/app/services/streaming_service.py
services/audio-lang-detection-service/app/core/config.py
services/config-service/main.py
services/config-service/registry/zookeeper_client.py
services/config-service/routers/config_router.py
services/config-service/tests/conftest.py
services/dashboard-service/main.py
services/language-detection-service/app/core/config.py
services/language-diarization-service/app/core/config.py
services/language-diarization-service/app/main.py
services/llm-service/app/clients/triton_client.py
services/llm-service/app/core/config.py
services/llm-service/app/main.py
services/metrics-service/main.py
services/ner-service/app/core/config.py
services/nmt-service/app/clients/model_management_client.py
services/nmt-service/app/core/config.py
services/nmt-service/app/services/smr_service.py
services/nmt-service/app/utils/try_it_utils.py
services/nmt-service/tests/test_triton_models.py
services/ocr-service/app/core/config.py
services/pii-service/main.py
services/pipeline-service/app/clients/http_client.py
services/pipeline-service/app/clients/service_registry_client.py
services/pipeline-service/app/core/config.py
services/pipeline-service/app/main.py
services/pipeline-service/app/routes/pipeline.py
services/policy-service/app/db/session.py
services/policy-service/app/services/policy_service.py
services/smr-service/db_connection.py
services/smr-service/main.py
services/speaker-diarization-service/app/core/config.py
services/telemetry-service/main.py
services/telemetry-service/routers/observability_router.py
services/transliteration-service/app/core/config.py
services/tts-service/app/core/config.py
services/tts-service/app/services/smr_service.py
```

41 service files across 22 services + 17 internal lib files (across 5
other shared libs). One of the most-imported shared libs in the
platform.

```
$ git grep -lE "^\s*(from|import)\s+ai4icore_core\.env" \
    -- 'services/**.py' 'libs/**.py' ':!libs/ai4icore_core/ai4icore_core/env/**'
libs/ai4icore_core/ai4icore_core/logging/...                  # internal mirrors only
libs/ai4icore_core/ai4icore_core/telemetry/...                # internal mirrors only
libs/ai4icore_core/ai4icore_core/model_management/...         # internal mirrors only
libs/ai4icore_core/ai4icore_core/observability/...            # internal mirrors only
libs/ai4icore_core/ai4icore_core/service_base/...             # internal mirrors only
```

— no service-level matches.
