# Removing `ai4icore_env` — Plan & Field Inventory

**Goal:** Eliminate `libs/ai4icore_env/` and move its responsibilities
either (a) into per-service local pydantic-settings classes, or
(b) into the shared lib that owns that domain (logging → `LoggingConfig`,
telemetry → `TelemetryConfig`, etc.).
**Generated:** 2026-05-18

---

## 0. TL;DR

`AppEnv` declares **226 fields**. Of those:

| Bucket | Count | Disposition |
|---|---:|---|
| **Dead** — defined but no `app_env.<x>` reference anywhere | ~91 | **Delete outright.** Includes ~30 zombie service-URL fields, all 11 per-service `triton_endpoint_*` fields, JWT/SMTP fields auth-service has already moved into its own `AuthSettings`, OAuth fields nobody reads, etc. |
| **Lib-internal** — used only by one of the four shared libs (`ai4icore_logging`, `ai4icore_telemetry`, `ai4icore_observability`, `ai4icore_model_management`, `ai4icore_service_base`); no service reads them directly | ~40 | **Move into that lib's existing local settings class** (each lib already has one — `LoggingConfig`, `TelemetryConfig`, `PluginConfig`, `ModelManagementConfig`). The lib reads its env vars directly via its own pydantic-settings class instead of going through `app_env`. |
| **Service-specific** — read by 1–2 services and nobody else | ~70 | **Move into a per-service `app/core/config.py`** that declares only the fields that service needs. The pattern is already established in `auth-service`, `platform-core-service`, `policy-service`. |
| **Genuinely shared** — read by ≥3 services (the platform-infra fields: Postgres, Redis, Kafka brokers, service identity, logging level) | ~25 | **Two options:** either (A) duplicate the ~25 declarations in each service's local `Settings(BaseSettings)` (each service is self-contained, no shared lib needed), or (B) keep a *much smaller* shared `PlatformInfraSettings` mixin (~25 fields) instead of the current 226-field god class. Recommendation: **Option A**, because the duplication is mechanical and gets us to "no shared env lib." |

**Removal is feasible.** The hard part isn't size — it's the **two
transitively-coupled mechanisms**:

1. **Shared libs reading from `app_env`.** Every `from ai4icore_env import app_env` inside `ai4icore_logging`, `ai4icore_telemetry`, `ai4icore_observability`, `ai4icore_model_management`, and `ai4icore_service_base` has to be replaced with that lib's own pydantic-settings instance.
2. **Module-load-time validation.** `app_env = AppEnv()` is constructed at import time, so missing env vars surface at process start. The new per-service `Settings()` instantiations need the same lifecycle so we don't push validation errors to request time.

---

## 1. Inventory — every field by usage

The full per-field map is in [Appendix A](#appendix-a--full-field-map).
Below is the bucketed view.

### 1.A — Genuinely shared (3+ services, or 1 service + ≥2 libs)

These are the platform-infra fields. If we wanted to keep a *small*
shared lib, these would be its content. Recommendation is still to
duplicate them per-service:

| Field | Services | Libs | Notes |
|---|---|---|---|
| `service_name` | 4 (alert-config-sync, alert-management, config, pipeline) | 4 (core, logging, service_base, telemetry) | Service identity. Each service knows its own name; could be a hardcoded constant per-service instead of an env var. |
| `service_version` | 0 | 3 (core, logging, telemetry) | Same — services know their own version. |
| `service_instance_id` | 2 (config, pipeline) | 2 (core, service_base) | Required for service registry; each service-base consumer needs this. |
| `service_port` / `service_host` / `service_public_url` | 1–2 (pipeline, config) | 2 (core, service_base) | Service-registry bookkeeping. |
| `environment` | 2 (alert-config-sync, alert-management) | 2 (core, logging) | Stage/env tag. |
| `log_level` / `root_log_level` | 1 (pipeline) | 2 (core, logging) | Lives naturally inside `LoggingConfig`. |
| `use_kafka_logging` | 3 (alert-config-sync, alert-management, pipeline) | 3 (core, logging, service_base) | Logging-related — into `LoggingConfig`. |
| `kafka_bootstrap_servers` | 2 (alerting, config) | 2 (core, logging) | Into `LoggingConfig` (and alerting's own settings). |
| `get_database_url()` (method) | 5 (alerting, config, dashboard, metrics, telemetry) | 2 (core, service_base) | The 5 services using this are exactly the ones with no `app/core/config.py` yet — they read `postgres_*` via `app_env.get_database_url()`. Each service can declare its own postgres fields. |
| `get_redis_url()` (method) | 5 (alerting, config, dashboard, metrics, telemetry) | 0 | Same. |
| `postgres_user/password/host/port/db` | 2 directly (alert-config-sync, alert-management) + 5 indirectly via `get_database_url()` | 0 | Platform-infra. Either duplicate or push into a `PlatformDBSettings` mixin. |
| `redis_host/port/password/db/timeout` | 1 (pipeline) | 2 (core, service_base) | Read by `service_base`, so every service-base consumer needs them transitively. |
| `db_pool_size`, `db_max_overflow` | 0 | 2 (core, service_base) | Only read by service_base. Move into service_base's own settings. |
| `rate_limit_per_minute` / `per_hour` | 1–2 (pipeline, request-profiler) | 2 (core, service_base) | Into service_base settings. |
| `try_it_limit` / `try_it_ttl_seconds` | 1 (nmt) | 0 | Single-consumer; ostensibly "shared" by name only. Move to nmt-service. |
| `port` (generic port for misc services) | 3 (alert-config-sync, alert-management, smr) | 0 | Each can declare its own. |

### 1.B — Lib-internal only (no service reads it directly)

These fields are read by exactly one shared lib and zero services.
They should live inside that lib's local settings class.

**`ai4icore_logging`** (~15 fields):
```
log_level, root_log_level, allowed_log_levels, min_log_level,
exclude_health_logs, exclude_metrics_logs, exclude_options_logs,
include_4xx_logs, request_logging_middleware_enabled,
request_log_include_paths, logging_plugin_enabled,
correlation_middleware_enabled, correlation_header_name,
kafka_log_topic, use_kafka_logging  (+ service_name, service_version, env)
```
The lib already has a `LoggingConfig` class — these fields belong there.

**`ai4icore_telemetry`** (~10 fields):
```
telemetry_enabled, telemetry_filter_http_spans,
telemetry_instrument_fastapi, telemetry_instrument_httpx,
telemetry_instrument_requests, telemetry_ip_capture_enabled,
jaeger_endpoint, jaeger_query_base_path, jaeger_query_url,
opensearch_url/username/password
```
The lib already has a `TelemetryConfig` — merge.

**`ai4icore_observability`** (~16 fields):
```
observe_util_enabled, observe_util_debug, observe_util_health_path,
observe_util_metrics_path, observe_util_metrics_update_interval,
observe_util_system_metrics_interval, observe_util_collect_*,
observe_util_max_completed_requests, observe_util_response_time_target,
observe_util_throughput_target, observe_util_availability_target,
observe_util_apps, observe_util_customers
```
The lib already has a `PluginConfig` — merge.

**`ai4icore_model_management`** (~8 fields):
```
model_management_cache_ttl, triton_endpoint_cache_ttl, triton_api_key,
model_management_health_gate_*, endpoint_validation_*
```
The lib already has `ModelManagementConfig` — merge.

**`ai4icore_service_base.app_factory`** (~12 fields):
```
db_pool_size, db_max_overflow, redis_*, rate_limit_*,
service_name, service_version, service_port, service_host,
service_public_url, service_instance_id, log_level
```
The factory currently reads these directly off `app_env`. Either (a)
the factory accepts a `ServiceBaseConfig` object as input, or (b) the
factory declares its own `BaseSettings`. (a) is cleaner.

### 1.C — Service-specific (used by 1 service only)

These are clear-cut: move into that service's own `app/core/config.py`.

**`config-service`** (~20 fields):
```
zookeeper_hosts, zookeeper_base_path, zookeeper_session_timeout,
zookeeper_connection_timeout,
health_check_*  (7 fields: timeout, additional_endpoints, max_retries,
                 initial_retry_delay, max_retry_delay, retry_backoff,
                 service_health_check_enabled, service_health_check_interval),
kafka_topic_config_updates, test_redis_url, service_instance_id,
service_port, get_database_url(), get_redis_url(), service_name
```

**`alert-config-sync-service`** (~21 fields):
```
postgres_*, auth_db_name, prometheus_url,
prometheus_application_alerts_path,
prometheus_infrastructure_alerts_path,
alertmanager_url, alertmanager_config_path, alert_sync_enabled,
sync_interval, smtp_*  (4 SMTP fields: smarthost, from, auth_username,
                        auth_password), default_receiver_emails,
alert_management_service_url, service_name, environment, port,
use_kafka_logging
```

**`alert-management-service`** (~10 fields):
```
postgres_*, alert_config_sync_service_url, port, service_name,
environment, use_kafka_logging
```

**`telemetry-service`** (~10 fields):
```
opensearch_url/username/password, elasticsearch_url/username/password,
jaeger_query_url, get_auth_database_url(), get_database_url(),
get_redis_url()
```

**`pipeline-service`** (~19 fields):
```
api_gateway_url, asr_service_url, tts_service_url, nmt_service_url,
pipeline_http_timeout, redis_host/port/password/timeout,
rate_limit_per_minute, rate_limit_per_hour, service_host, service_port,
service_public_url, service_instance_id, service_name, log_level,
use_kafka_logging, config_service_url
```

**`smr-service`** (~10 fields):
```
postgres_user/password, app_db_host/port/name, llm_translate_api_url,
policy_engine_url, request_profiler_service_url, model_management_service_url,
port, reload
```

**`nmt-service`** (~6 fields):
```
triton_endpoint, model_management_service_url,
model_management_service_api_key, smr_service_url,
try_it_limit, try_it_ttl_seconds
```

**`llm-service`** (~2 fields):
```
triton_endpoint, triton_timeout
```

**`asr-service`** (~5 fields):
```
allow_anonymous_access, require_api_key, smr_enabled,
smr_service_url, auth_enabled
```

**`tts-service`** (~1 field):
```
smr_service_url
```

**`dashboard-service`** (~6 fields):
```
influxdb_url/token/org/bucket, streamlit_port, get_database_url(),
get_redis_url()
```

**`metrics-service`** (~5 fields):
```
influxdb_url/token/org/bucket, get_database_url(), get_redis_url(),
service_name
```

**`alerting-service`** (~3 fields):
```
kafka_bootstrap_servers, get_database_url(), get_redis_url()
```

**`policy-service`** (~3 fields):
```
policy_service_http_timeout, auth_service_url, get_app_database_url()
```

**`request-profiler`** (~5 fields):
```
rate_limit_per_minute, complexity_model_path, domain_model_path,
max_batch_size, max_text_length
```
**⚠ Bug found**: `complexity_model_path`, `domain_model_path`,
`max_batch_size`, `max_text_length` are referenced as `app_env.<x>` in
[services/request-profiler/main.py:72](../services/request-profiler/request_profiler/main.py#L72)
but **not declared in `AppEnv`**. `AppEnv` has `extra="ignore"` so these
attribute reads raise `AttributeError` at runtime. The service has its
own `Settings(BaseSettings)` at `request_profiler/config.py` with these
fields — the bug is the `app_env.<x>` reads (should be `settings.<x>`).
Fix separately.

### 1.D — Dead fields (defined, never referenced)

~91 fields in `AppEnv` are defined but no `app_env.<x>` reference exists
anywhere in the repo. The full list:

```
access_token_expire_minutes, ai4i_platform_db_name, alerting_service_url,
allow_deprecated_model_changes, api_gateway_timeout, api_key_cache_ttl,
api_key_encryption_key, api_permissions_json_path, app_db_password,
app_db_user, audio_lang_detection_service_url, auth_database_url,
auth_db_host, auth_db_password, auth_db_port, auth_db_user,
auth_http_timeout, bypass_cache, cors_origins, dashboard_service_url,
database_url, default_service_timeout_seconds, endpoint_validation_mode,
endpoint_validation_skip_tls_verify, endpoint_validation_timeout_seconds,
from_email, frontend_url, github_client_id, google_client_id,
google_client_secret, google_redirect_uri, inference_ssl_verify,
influxdb_bucket, jaeger_ui_url, jwks_path, jwks_url, jwt_algorithm,
jwt_audience, jwt_issuer, jwt_issuer_url, jwt_refresh_secret_key,
jwt_secret_key, language_detection_service_url,
language_diarization_service_url, llm_service_url,
load_balancer_algorithm, max_active_versions_per_model,
max_consecutive_failures, metrics_service_url, migration_db_host,
migration_db_port, model_management_api_key,
model_management_health_gate_cache_ttl_seconds,
model_management_health_gate_enabled,
model_management_health_gate_timeout_seconds, ner_service_timeout_seconds,
ner_service_url, ocr_service_url, pii_redact_timeout, pii_service_url,
pipeline_service_url, postgres_db, refresh_token_expire_days,
refresh_token_expire_hours, restore_db_host, restore_db_port,
run_inference_test, runtime_env, sendgrid_api_key, service_registry_ttl,
simple_ui_url, smtp_from_alerts, smtp_from_noreply, smtp_host,
smtp_password, smtp_port, smtp_reply_to, smtp_tls, smtp_username,
speaker_diarization_service_url, streaming_response_frequency_ms,
swagger_server_url, telemetry_service_url, test_database_url,
transliteration_service_url, triton_endpoint_asr,
triton_endpoint_audio_langdetect, triton_endpoint_lang_diarization,
triton_endpoint_langdetect, triton_endpoint_llm, triton_endpoint_ner,
triton_endpoint_nmt, triton_endpoint_ocr,
triton_endpoint_speaker_diarization, triton_endpoint_transliteration,
triton_endpoint_tts
```

Notable groups inside this:

- **All 11 `triton_endpoint_<service>` fields** are unused. Per-service triton endpoints come from the model-management service at request time, not from env.
- **All but one of the `<service>_service_url` fields** (12 of them) — only the ones actively consumed by pipeline/smr/alert services are alive; the rest are zombies.
- **The full JWT + OAuth stack** (`jwt_secret_key`, `jwks_url`, `google_client_id`, etc.) — auth-service moved to its own `AuthSettings` and these are leftover.
- **The full secondary SMTP stack** (`smtp_host`, `smtp_port`, `smtp_username`, etc.) — alert-config-sync uses the `smtp_smarthost`/`smtp_auth_*` set; this parallel set is unused. Same for `sendgrid_api_key`, `from_email`.
- **Migration/restore DB fields** — used by standalone scripts in `infrastructure/databases/cli.py` if at all, not by services.

**Phase 0 of the plan is to delete these 91 fields.** Zero-risk.

---

## 2. Reproducible counting

```bash
# Build the list of fields referenced as app_env.<x> anywhere
grep -rEhno "app_env\.[a-zA-Z_][a-zA-Z0-9_]*" services/ libs/ --include='*.py' \
  | sed 's/.*app_env\.//' | sort -u > /tmp/used.txt

# Build the list of fields declared in AppEnv
grep -E "^    [a-z_][a-zA-Z0-9_]*:" libs/ai4icore_env/ai4icore_env/settings.py \
  | awk -F: '{print $1}' | tr -d ' ' | sort -u > /tmp/defined.txt

# Dead fields
comm -13 /tmp/used.txt /tmp/defined.txt

# Per-field consumers
for f in $(cat /tmp/used.txt); do
  grep -rlE "app_env\.${f}\b" services/ libs/ --include='*.py' \
    | awk -F/ '/services\//{print "svc:"$2} /libs\//{print "lib:"$2}' \
    | sort -u | tr '\n' ',' | sed "s/^/$f: /; s/,$//"
  echo
done
```

The reference numbers in §1 came from running exactly these commands.

---

## 3. Where each field lands — target schemas

### 3.A — Library-owned settings (already have classes, just merge fields in)

Each of the four consuming libs already has a local pydantic-settings
class. Today those classes either (a) duplicate fields with defaults
read off `app_env`, or (b) the lib imports `app_env` directly. The
target shape:

#### `ai4icore_logging` → expand existing `LoggingConfig`

```python
# libs/ai4icore_logging/ai4icore_logging/config.py
class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # already there:
    service_name: str = ""
    service_version: str = "1.0.0"
    environment: str = "development"
    log_level: str = "INFO"

    # to fold in from AppEnv:
    root_log_level: Optional[str] = None
    min_log_level: str = "INFO"
    allowed_log_levels: str = ""
    exclude_health_logs: bool = False
    exclude_metrics_logs: bool = False
    exclude_options_logs: bool = False
    include_4xx_logs: bool = False
    logging_plugin_enabled: bool = True
    request_logging_middleware_enabled: bool = True
    request_log_include_paths: str = ""
    correlation_middleware_enabled: bool = True
    correlation_header_name: str = ""
    use_kafka_logging: bool = False
    kafka_bootstrap_servers: str = ""
    kafka_log_topic: str = ""
```

The handlers/formatters/middleware then read `LoggingConfig()` directly
instead of `from ai4icore_env import app_env`.

#### `ai4icore_telemetry` → expand existing `TelemetryConfig`

```python
class TelemetryConfig(BaseSettings):
    telemetry_enabled: bool = True
    telemetry_filter_http_spans: bool = False
    telemetry_instrument_fastapi: bool = True
    telemetry_instrument_httpx: bool = False
    telemetry_instrument_requests: bool = False
    telemetry_ip_capture_enabled: bool = False
    jaeger_endpoint: str = ""
    jaeger_query_base_path: str = ""
    jaeger_query_url: str = ""
    opensearch_url: Optional[str] = None
    opensearch_username: Optional[str] = None
    opensearch_password: Optional[str] = None
    service_name: str = ""
    service_version: str = "1.0.0"
```

#### `ai4icore_observability` → expand existing `PluginConfig`

```python
class PluginConfig(BaseSettings):
    observe_util_enabled: bool = False
    observe_util_debug: bool = False
    observe_util_health_path: str = "/health"
    observe_util_metrics_path: str = "/metrics"
    observe_util_metrics_update_interval: int = 60
    observe_util_system_metrics_interval: int = 30
    observe_util_collect_system_metrics: bool = True
    observe_util_collect_gpu_metrics: bool = False
    observe_util_collect_db_metrics: bool = False
    observe_util_max_completed_requests: int = 1000
    observe_util_response_time_target: float = 1.0
    observe_util_throughput_target: float = 100.0
    observe_util_availability_target: float = 99.9
    observe_util_apps: str = ""
    observe_util_customers: str = ""
```

#### `ai4icore_model_management` → expand existing `ModelManagementConfig`

```python
class ModelManagementConfig(BaseSettings):
    model_management_service_url: str = ""
    model_management_service_api_key: Optional[str] = None
    model_management_cache_ttl: int = 300
    triton_endpoint: Optional[str] = None
    triton_api_key: Optional[str] = None
    triton_endpoint_cache_ttl: int = 300
    config_service_url: str = ""  # for the optional health gate
```

#### `ai4icore_service_base` → new `ServiceBaseConfig`

`service_base.app_factory` currently reads ~12 fields off `app_env`. It
should accept a `ServiceBaseConfig` argument or instantiate its own:

```python
class ServiceBaseConfig(BaseSettings):
    service_name: str = ""
    service_version: str = "1.0.0"
    service_port: int = 8080
    service_host: Optional[str] = None
    service_public_url: Optional[str] = None
    service_instance_id: Optional[str] = None
    log_level: str = "INFO"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    redis_host: str = ""
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_timeout: int = 10
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
```

Each service that calls `create_inference_app(...)` would either pass
in a config object explicitly, or rely on the factory instantiating
its own `ServiceBaseConfig()` which reads the env at process start.

### 3.B — Per-service local config

Three services already have local config classes — those are the
templates. The other ~22 services need their own `app/core/config.py`
declaring exactly the fields they reference.

The full per-service target schemas are in [Appendix B](#appendix-b--per-service-target-config-files).

---

## 4. Migration sequence

### Phase 0 — Delete dead fields (zero-risk)

Remove the ~91 dead fields from `AppEnv` (§1.D). No consumer reads
them, so nothing breaks.

Estimated effort: 1 hour. Single PR.

### Phase 1 — Bug fix in request-profiler

`request_profiler/main.py:72` references `app_env.domain_model_path`
and `app_env.complexity_model_path`. Those don't exist on `AppEnv`.
The service already has the right values on its local `Settings` —
the bug is the `app_env.` prefix. Replace with the local `settings.`.

Estimated effort: 30 minutes. Standalone PR.

### Phase 2 — Library-internal extraction (per lib, ~5 PRs)

For each consuming lib in this order:

1. **`ai4icore_observability`** — smallest, fully self-contained. Move the 15 `observe_util_*` fields into `PluginConfig`. Stop importing `app_env`. Bump the lib version.
2. **`ai4icore_telemetry`** — move the 10 telemetry/jaeger/opensearch fields into `TelemetryConfig`. Stop importing `app_env`.
3. **`ai4icore_model_management`** — move the 8 fields into `ModelManagementConfig`. Stop importing `app_env`.
4. **`ai4icore_logging`** — move the 15 logging-related fields into `LoggingConfig`. Stop importing `app_env`. This one is highest-impact because every service consumes logging transitively.
5. **`ai4icore_service_base`** — move the 12 fields into a new `ServiceBaseConfig`. The `app_factory` either instantiates it or accepts it as a parameter. Stop importing `app_env`.

After Phase 2, **no lib in `libs/` imports `ai4icore_env`**. The only
remaining consumers are the services themselves.

Each PR is independent and can ship one at a time. Risk per PR is
bounded to one lib's surface.

### Phase 3 — Per-service extraction (per service, ~22 PRs)

For each service that currently does `from ai4icore_env import app_env`:

1. Create `app/core/config.py` (or extend an existing one) with a
   `Settings(BaseSettings)` declaring exactly the fields the service
   references (see [Appendix B](#appendix-b--per-service-target-config-files)).
2. Replace every `from ai4icore_env import app_env` with
   `from app.core.config import settings`.
3. Replace every `app_env.<field>` with `settings.<field>`.
4. For `app_env.get_database_url()` / `get_redis_url()` /
   `get_app_database_url()` / `get_auth_database_url()` — port the
   URL-builder methods onto the local `Settings` class.
5. Remove the lib install from the service Dockerfile and the bind-mount from `docker-compose-local.yml`.
6. Remove `ai4icore-env` from `requirements.txt` (if listed).

Services in suggested rollout order (smallest first to validate the
pattern, then escalate):

| Order | Service | Fields | Reason |
|---|---|---:|---|
| 1 | `tts-service` | 1 | Smallest. |
| 2 | `llm-service` | 2 | Tiny. |
| 3 | `alerting-service` | 3 | Tiny + uses `get_database_url`/`get_redis_url`. Validates URL-builder port. |
| 4 | `policy-service` | 3 | Already has partial local config (`app/db/config.py`); merge. |
| 5 | `asr-service` | 5 | |
| 6 | `request-profiler` | 5 | Already has local `Settings`; just remove `app_env.` references. |
| 7 | `metrics-service` | 5 | |
| 8 | `nmt-service` | 6 | |
| 9 | `dashboard-service` | 6 | |
| 10 | `alert-management-service` | 10 | |
| 11 | `smr-service` | 10 | |
| 12 | `telemetry-service` | 10 | |
| 13 | `pipeline-service` | 19 | Largest direct consumer. |
| 14 | `config-service` | 20 | |
| 15 | `alert-config-sync-service` | 21 | Largest direct consumer. |

Plus the inference services that install the lib but don't import it
(`audio-lang-detection`, `language-detection`, `language-diarization`,
`ner`, `ocr`, `speaker-diarization`, `transliteration`, `pii`) —
these just need the Dockerfile/compose cleanup since they don't
import `app_env`.

### Phase 4 — Delete the lib

Once Phases 2 and 3 are done, `grep -rln "ai4icore_env" services/ libs/`
should return empty (except inside the lib itself). At that point:

1. Delete `libs/ai4icore_env/` from the repo.
2. Remove the package from any remaining `pyproject.toml` / `requirements.txt`.
3. Remove any remaining bind-mounts from `docker-compose-local.yml`.
4. Remove any `COPY libs/ai4icore_env` / `pip install -e ai4icore_env`
   lines from Dockerfiles.

---

## 5. Risks & gotchas

1. **`app_env` is constructed at import time.** Every replacement
   `Settings()` must also be instantiated at module load (not lazily) so
   env-validation errors continue to surface at process start, not at
   request time. The pattern in `auth-service/app/core/config.py`
   (`settings = AuthSettings()` at module bottom) is the right shape —
   copy it.

2. **The factories use `app_env` to populate plugin configs.** For
   example, `ai4icore_service_base.app_factory` does:
   ```python
   mm_config = ModelManagementConfig(
       model_management_service_url=app_env.model_management_service_url,
       ...
   )
   ```
   After Phase 2 (when `ModelManagementConfig` reads env directly), the
   factory just does `mm_config = ModelManagementConfig()`. Same for
   logging/telemetry/observability — the factory's wiring code gets
   simpler, not harder.

3. **Duplication of `service_name` / `service_version` / `environment`
   across every local Settings class.** This is the cost of removing the
   shared lib. Each service ends up declaring these ~3 fields
   identically. Either accept the duplication (recommended — it's
   ~3 lines per service) or extract a tiny `ServiceIdentityMixin` that
   each service's Settings inherits. The mixin approach reintroduces a
   shared module; if the goal is removal, just duplicate.

4. **Many fields in `AppEnv` have empty-string defaults instead of
   `Optional[str] = None`.** When porting to per-service classes,
   tighten the type — required string env vars should be
   `Field(..., env="FOO")` (no default) so the service fails fast at
   startup when the env var is missing. The current pattern of `host: str = ""`
   silently leaves you with `""` as a host and the failure surfaces
   later at connection time.

5. **`AppEnv._resolve_fallbacks`** (the `@model_validator`) cross-wires
   `app_db_*` and `auth_db_*` to fall back to `postgres_*`. When
   splitting per-service, that fallback chain has to be re-implemented
   in each consumer that needs it (today only `smr-service` and
   `telemetry-service` rely on it). Or just inline the fallback into the
   URL builder method on the local Settings class.

6. **Per-service test runners may import `app_env`.** Some `conftest.py`
   files import it (e.g. `config-service/tests/conftest.py`). Migrate
   tests alongside their service.

7. **Production deployment env files don't change.** Removing the
   library doesn't change what env vars need to be set in any given
   service's `.env` or k8s ConfigMap — it only changes how that service
   reads them.

---

## Appendix A — Full field map

The complete table of every `AppEnv` field, the services that read it,
and the libs that read it is at the head of §1. Reproducible via the
shell snippet in §2.

## Appendix B — Per-service target config files

A concrete `Settings` class skeleton for each service is in §1.C. Below
are the inference services' minimal target configs (most of them have
2–6 fields max):

```python
# services/tts-service/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    smr_service_url: str = ""

settings = Settings()
```

```python
# services/llm-service/app/core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    triton_endpoint: Optional[str] = None
    triton_timeout: float = 300.0

settings = Settings()
```

```python
# services/nmt-service/app/core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    triton_endpoint: Optional[str] = None
    model_management_service_url: str = ""
    model_management_service_api_key: Optional[str] = None
    smr_service_url: str = ""
    try_it_limit: int = 5
    try_it_ttl_seconds: int = 3600

settings = Settings()
```

Each of the other services in §1.C maps the same way — its `Settings`
class declares one field per `app_env.<x>` reference, with the
appropriate default.
