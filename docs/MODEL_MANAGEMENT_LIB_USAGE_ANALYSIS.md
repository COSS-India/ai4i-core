# `ai4icore_model_management` — Usage Analysis

**Status:** Factual map of who uses the lib (direct and transitive) and who doesn't.
**Generated:** 2026-05-15

---

## TL;DR

`ai4icore_model_management` is consumed by exactly **11 inference services**:

```
asr-service, audio-lang-detection-service, language-detection-service,
language-diarization-service, llm-service, ner-service, nmt-service,
ocr-service, speaker-diarization-service, transliteration-service, tts-service
```

— directly (each service's `app/clients/triton_client.py` subclasses
`TritonClient`) and transitively (their `create_inference_app(...)` call
into `ai4icore_service_base` pulls in `ModelManagementPlugin`,
`AuthContextMiddleware`, and `ModelManagementConfig`).

**Outside the 11 inference services, only `pipeline-service` uses
`ai4icore_service_base` at all** — and it deliberately imports only
`RateLimitMiddleware`, `ServiceRegistryClient`, and `create_health_router`,
**none** of which trigger the lazy `create_inference_app` import path that
loads `ai4icore_model_management`. `pipeline-service` therefore **does not**
end up depending on `ai4icore_model_management` even transitively, and its
Dockerfile/requirements correctly do not install it.

Every other service in the repo (auth, platform-core, model-management
itself, policy, telemetry, metrics, pay-per-use, pii, smr, dashboard,
docs-manager, alerting, alert-management, alert-config-sync, api gateways,
request-profiler, multi-tenant-feature, config-service) has **zero**
references to either `ai4icore_model_management` or `ai4icore_service_base`
— in code, in Dockerfile, in requirements, in compose. The only stray
non-inference reference anywhere is one dead `docker-compose-local.yml`
bind-mount on `alert-management-service` (no matching code), which is
copy/paste leftover.

---

## 1. What the lib provides

Source: [libs/ai4icore_model_management/ai4icore_model_management/](../libs/ai4icore_model_management/ai4icore_model_management/)

| Module | LOC | Public surface | Purpose |
|---|---:|---|---|
| `client.py` | 501 | `ModelManagementClient` | HTTP client for `model-management-service`. Three-layer cache (in-memory → Redis → API) keyed by `serviceId`. |
| `triton_client.py` | 381 | `TritonClient`, `_current_scope`, `_accumulate_inference_time`, `SCOPE_KEY`, `resolve_inference_ssl_verify` | Generic Triton-HTTP wrapper. Tracks per-request cumulative inference time via a `ContextVar` so middleware can stamp the `X-Inference-Model-Time` response header. |
| `middleware.py` | 854 | `ModelResolutionMiddleware` | Extracts `config.serviceId` from request body → resolves to Triton endpoint + model name via `ModelManagementClient` → instantiates a `TritonClient` → attaches all of it to `request.state`. Also implements the optional `MODEL_MANAGEMENT_HEALTH_GATE_*` pre-flight check that fails 503 when the backend health snapshot is `unhealthy`. |
| `auth_context_middleware.py` | 34 | `AuthContextMiddleware` | Forwards auth headers from the inbound request to downstream resolution calls. |
| `plugin.py` | 97 | `ModelManagementPlugin` | One-call wiring helper that registers `ModelResolutionMiddleware`, attaches a `ModelManagementClient` to `app.state`, and binds a sync-Redis client. |
| `config.py` | 90 | `ModelManagementConfig` | Pydantic-settings config (env-driven). |
| `__init__.py` | 38 | re-exports | — |
| **Total** | **1,995** | | |

---

## 2. Who consumes it

### 2.1 Inference services — direct imports

Eleven services import directly from `ai4icore_model_management`. The pattern
is **uniform** — each has an `app/clients/triton_client.py` file that
subclasses `TritonClient` to add service-specific I/O preparation, plus the
Dockerfile installs the lib at build time.

| Service | Direct imports | What they use it for |
|---|---|---|
| `asr-service` | [`app/clients/triton_client.py:10`](../services/asr-service/app/clients/triton_client.py#L10) — `from ai4icore_model_management import TritonClient` | `ASRTritonClient(TritonClient)` — adds ASR-specific tensor prep. |
| `audio-lang-detection-service` | [`app/clients/triton_client.py:9`](../services/audio-lang-detection-service/app/clients/triton_client.py#L9) | Same pattern: `*TritonClient(TritonClient)` subclass. |
| `language-detection-service` | [`app/clients/triton_client.py:9`](../services/language-detection-service/app/clients/triton_client.py#L9) | Same. |
| `language-diarization-service` | [`app/clients/triton_client.py:11`](../services/language-diarization-service/app/clients/triton_client.py#L11) | Same. |
| `ner-service` | [`app/clients/triton_client.py:7`](../services/ner-service/app/clients/triton_client.py#L7) | Same. |
| `nmt-service` | [`app/clients/triton_client.py:7`](../services/nmt-service/app/clients/triton_client.py#L7) + [`tests/test_triton_models.py:25`](../services/nmt-service/tests/test_triton_models.py#L25) | `NMTTritonClient(TritonClient)`; tests use `TritonClient` and `ModelManagementClient` directly. |
| `ocr-service` | [`app/clients/triton_client.py:9`](../services/ocr-service/app/clients/triton_client.py#L9) | Same pattern. |
| `speaker-diarization-service` | [`app/clients/triton_client.py:9`](../services/speaker-diarization-service/app/clients/triton_client.py#L9) | Same. |
| `transliteration-service` | [`app/clients/triton_client.py:10`](../services/transliteration-service/app/clients/triton_client.py#L10) | Same. |
| `tts-service` | [`app/clients/triton_client.py:9`](../services/tts-service/app/clients/triton_client.py#L9) | Same. |
| `llm-service` | [`app/clients/triton_client.py:16-19`](../services/llm-service/app/clients/triton_client.py#L16-L19) — `from ai4icore_model_management.triton_client import _accumulate_inference_time, resolve_inference_ssl_verify` | LLM service does **not** subclass `TritonClient` because it talks to an external HTTP LLM endpoint via `httpx`, not native Triton. But it still wants the ContextVar-based timing accumulator so the `X-Inference-Model-Time` response header lights up, and the SSL-verify helper. |

### 2.2 Inference services — transitive via `ai4icore_service_base`

All eleven services above call `create_inference_app(...)` from
`ai4icore_service_base` ([libs/ai4icore_service_base/ai4icore_service_base/app_factory.py:42-46](../libs/ai4icore_service_base/ai4icore_service_base/app_factory.py#L42-L46)):

```python
from ai4icore_model_management import (
    AuthContextMiddleware,
    ModelManagementConfig,
    ModelManagementPlugin,
)
```

Inside the factory ([app_factory.py:376-396](../libs/ai4icore_service_base/ai4icore_service_base/app_factory.py#L376-L396)) this wires up:

* `ModelManagementPlugin(config=...).register_plugin(app, redis_client=...)`
  → installs `ModelResolutionMiddleware` and attaches the cached
  `ModelManagementClient` to `app.state`.
* `app.add_middleware(AuthContextMiddleware, path_prefixes=[...])`.

So **every inference service consumes the lib transitively**, even before the
direct `TritonClient` subclassing in §2.1.

Additionally, [libs/ai4icore_service_base/ai4icore_service_base/inference_headers.py:18](../libs/ai4icore_service_base/ai4icore_service_base/inference_headers.py#L18) imports `_current_scope, SCOPE_KEY` from `ai4icore_model_management.triton_client` so the `InferenceHeadersMiddleware` can stamp `X-Trace-Id` and `X-Inference-Model-Time` headers using the timing accumulated inside `TritonClient` calls. This is a tight runtime contract between the two libs.

### 2.3 Compose / Dockerfile bindings (operational, not code)

* **Dockerfile (build time):** every one of the 11 inference services has a
  `COPY libs/ai4icore_model_management /app/libs/ai4icore_model_management`
  + `RUN pip install --no-cache-dir --user -e /app/libs/ai4icore_model_management`
  stanza. Example: [services/nmt-service/Dockerfile:17,44](../services/nmt-service/Dockerfile#L17).
* **docker-compose-local.yml (dev hot-reload):** 12 services bind-mount
  `./libs/ai4icore_model_management:/app/libs/ai4icore_model_management` —
  the 11 inference services **plus `alert-management-service`**.
  `alert-management-service` does not import from the lib at all (verified by
  grep — see §4), so its mount is a **stale entry**, almost certainly a
  copy/paste leftover from when inference-service blocks in the compose file
  were duplicated. It is safe to delete that single line:

  ```yaml
  # docker-compose-local.yml — under alert-management-service.volumes
  - ./libs/ai4icore_model_management:/app/libs/ai4icore_model_management   # DEAD MOUNT — remove
  ```

---

## 3. Who uses `ai4icore_service_base` outside the 11 inference services?

Because the factory in `ai4icore_service_base` pulls in
`ai4icore_model_management`, the natural next question is: does any
non-inference service end up dragging in `model_management` simply by
importing `ai4icore_service_base`?

**Answer: only one non-inference service imports `ai4icore_service_base` at
all (`pipeline-service`), and it imports a deliberately narrow surface that
does NOT pull in `ai4icore_model_management`.**

### 3.1 The only non-inference consumer: `pipeline-service`

`pipeline-service` orchestrates calls across the inference services over
HTTP — it does not call Triton directly. It imports two pieces from
`ai4icore_service_base`:

| File | Import |
|---|---|
| [services/pipeline-service/app/main.py:14](../services/pipeline-service/app/main.py#L14) | `from ai4icore_service_base import RateLimitMiddleware, ServiceRegistryClient` |
| [services/pipeline-service/app/routes/health.py:3](../services/pipeline-service/app/routes/health.py#L3) | `from ai4icore_service_base import create_health_router` |

It **does not** import `create_inference_app`.

This matters because of how `ai4icore_service_base/__init__.py` is wired
([libs/ai4icore_service_base/ai4icore_service_base/__init__.py:10-20](../libs/ai4icore_service_base/ai4icore_service_base/__init__.py#L10-L20)):

```python
from .service_registry import ServiceRegistryClient
from .rate_limit import RateLimitMiddleware
from .health import create_health_router

# Lazy import: create_inference_app depends on ai4icore_model_management
# which is not installed in non-inference services (e.g. pipeline-service).
def __getattr__(name):
    if name == "create_inference_app":
        from .app_factory import create_inference_app
        return create_inference_app
    raise AttributeError(...)
```

`ServiceRegistryClient`, `RateLimitMiddleware`, and `create_health_router`
are imported eagerly at module load — and **none of them touch
`ai4icore_model_management`**. The only path that loads `app_factory.py`
(and therefore loads `ai4icore_model_management`) is an explicit access to
`create_inference_app`, gated behind the `__getattr__` lazy hook.

So `pipeline-service` consumes `ai4icore_service_base` **without** ending
up with `ai4icore_model_management` on its import graph. Its build
environment confirms this:

* `services/pipeline-service/Dockerfile` — no `COPY libs/ai4icore_model_management`, no `pip install ai4icore_model_management`.
* `services/pipeline-service/requirements.txt` — no `ai4icore_model_management` line.

The lazy-import design in `service_base/__init__.py` is **load-bearing for
exactly this case**, and the in-line comment even names `pipeline-service`
as the motivating example.

### 3.2 Every other service does not use `ai4icore_service_base` either

A repo-wide grep for `from ai4icore_service_base` / `import ai4icore_service_base`
returns exactly 24 hits across 24 files — and all of them are in the 11
inference services (`app/main.py` + `app/routes/health.py` per service)
plus the two `pipeline-service` files in §3.1.

```bash
$ grep -rnE "^\s*(from|import)\s+ai4icore_service_base" services/ --include='*.py'
# → 24 hits: 2 lines × (11 inference services + pipeline-service)
```

No other service in the repo touches `ai4icore_service_base` at all.

---

## 4. Who does **not** use `ai4icore_model_management`

Every non-inference service folder was scanned exhaustively for
`model_management`, `TritonClient`, `ModelManagementClient`,
`ModelResolutionMiddleware`, and the `ai4icore_model_management` import
string. Every one of them returned **zero hits in their own folder**:

| Service | Python imports | Dockerfile | requirements / pyproject | Uses `ai4icore_service_base`? | Notes |
|---|:---:|:---:|:---:|:---:|---|
| `auth-service` | ✗ | ✗ | ✗ | ✗ | |
| `auth-service-v2` | ✗ | ✗ | ✗ | ✗ | |
| `platform-core-service` | ✗ | ✗ | ✗ | ✗ | |
| `pipeline-service` | ✗ | ✗ | ✗ | **partial** | Uses `RateLimitMiddleware`, `ServiceRegistryClient`, `create_health_router` only — lazy-import design prevents `ai4icore_model_management` from being pulled in. See §3.1. |
| `model-management-service` | ✗ | ✗ | ✗ | ✗ | **It *is* the HTTP API the lib calls — by design, does not consume itself.** |
| `policy-service` | ✗ | ✗ | ✗ | ✗ | |
| `policy-engine` | ✗ | ✗ | ✗ | ✗ | |
| `pay-per-use-service` | ✗ | ✗ | ✗ | ✗ | |
| `pii-service` | ✗ | ✗ | ✗ | ✗ | |
| `telemetry-service` | ✗ | ✗ | ✗ | ✗ | |
| `metrics-service` | ✗ | ✗ | ✗ | ✗ | |
| `smr-service` | ✗ | ✗ | ✗ | ✗ | |
| `alert-management-service` | ✗ | ✗ | ✗ | ✗ | **Has a dead compose bind-mount — see below.** |
| `alert-config-sync-service` | ✗ | ✗ | ✗ | ✗ | |
| `alerting-service` | ✗ | ✗ | ✗ | ✗ | |
| `dashboard-service` | ✗ | ✗ | ✗ | ✗ | |
| `docs-manager` | ✗ | ✗ | ✗ | ✗ | |
| `request-profiler` | ✗ | ✗ | ✗ | ✗ | |
| `config-service` | ✗ | ✗ | ✗ | ✗ | Not a Python service. |
| `api-gateway-service` | ✗ | ✗ | ✗ | ✗ | nginx, not Python. |
| `api-gateway-legacy` | ✗ | ✗ | ✗ | ✗ | |
| `multi-tenant-feature` | ✗ | ✗ | ✗ | ✗ | |

**Verification command (reproducible):**

```bash
# Any code/config reference under a non-inference service folder?
for s in services/*/; do
  name=$(basename "$s")
  case " asr-service audio-lang-detection-service language-detection-service \
language-diarization-service llm-service ner-service nmt-service ocr-service \
speaker-diarization-service transliteration-service tts-service " in
    *" $name "*) continue;;
  esac
  hits=$(grep -rEln "ai4icore_model_management|TritonClient|ModelManagementClient" "$s" 2>/dev/null)
  [ -n "$hits" ] && { echo "[$name]"; echo "$hits"; }
done
# → empty output (confirmed 2026-05-15)
```

### The one and only stray non-inference reference

`alert-management-service` has **a single dead bind-mount** in
`docker-compose-local.yml` and **nothing else** — its Dockerfile,
`requirements.txt`, `main.py`, `routers/`, `utils/` were all scanned and
contain zero references.

```yaml
# docker-compose-local.yml — under alert-management-service.volumes
- ./libs/ai4icore_model_management:/app/libs/ai4icore_model_management   # DEAD — remove
```

Almost certainly copy/paste leftover from when inference-service blocks in
the compose file were duplicated. Removing this single line has no
functional impact.

**Conclusion:** the lib is consumed only by services that fan out to a
Triton inference backend. The one non-inference service that uses
`ai4icore_service_base` (`pipeline-service`) deliberately avoids the
`create_inference_app` factory and therefore avoids pulling
`ai4icore_model_management` in.

---

## 5. What the lib depends on

From [libs/ai4icore_model_management/pyproject.toml](../libs/ai4icore_model_management/pyproject.toml):

```
fastapi, starlette, httpx, pydantic, python-dotenv,
tritonclient[http], numpy, redis
```

`tritonclient[http]` and `numpy` are the heavy ones. They pin this lib to the
inference world — installing it in a non-inference service would drag
Triton client and NumPy unnecessarily into the image.

---

## 6. Why this lib sits awkwardly in `libs/`

1. **It looks platform-wide because of where it lives (`libs/`), but it isn't.**
   Eleven inference services use it; the rest don't and shouldn't (they don't
   call Triton).
2. **`ai4icore_service_base.app_factory` makes the dependency invisible to
   service authors.** A reader of `services/nmt-service/app/main.py` sees no
   `ai4icore_model_management` import — yet the running app installs
   `ModelResolutionMiddleware` and `AuthContextMiddleware` via the factory.
3. **There is a hidden runtime contract with `ai4icore_service_base`.**
   `inference_headers.py` reads ContextVars that `TritonClient` writes
   (`_current_scope` + `SCOPE_KEY`). The two libs cannot be versioned
   independently without breaking that contract.
4. **The lazy-import escape hatch in `ai4icore_service_base/__init__.py`
   exists exactly because of this.** It lets `pipeline-service` use the
   service_base lib without installing model_management. The fact that this
   workaround was necessary at all is a symptom of the awkward placement.

---

## 7. Appendix — quick-reference grep results

```
$ git grep -lE "ai4icore_model_management"
docker-compose-local.yml
libs/ai4icore_model_management/ai4icore_model_management/triton_client.py
libs/ai4icore_model_management/README.md
libs/ai4icore_model_management/pyproject.toml
libs/ai4icore_model_management/tests/...
libs/ai4icore_service_base/ai4icore_service_base/__init__.py
libs/ai4icore_service_base/ai4icore_service_base/app_factory.py
libs/ai4icore_service_base/ai4icore_service_base/inference_headers.py
services/asr-service/Dockerfile
services/asr-service/app/clients/triton_client.py
services/audio-lang-detection-service/Dockerfile
services/audio-lang-detection-service/app/clients/triton_client.py
services/language-detection-service/Dockerfile
services/language-detection-service/app/clients/triton_client.py
services/language-diarization-service/Dockerfile
services/language-diarization-service/app/clients/triton_client.py
services/llm-service/Dockerfile
services/llm-service/app/clients/triton_client.py
services/ner-service/Dockerfile
services/ner-service/app/clients/triton_client.py
services/nmt-service/Dockerfile
services/nmt-service/app/clients/triton_client.py
services/nmt-service/tests/test_triton_models.py
services/ocr-service/Dockerfile
services/ocr-service/app/clients/triton_client.py
services/speaker-diarization-service/Dockerfile
services/speaker-diarization-service/app/clients/triton_client.py
services/transliteration-service/Dockerfile
services/transliteration-service/app/clients/triton_client.py
services/tts-service/Dockerfile
services/tts-service/app/clients/triton_client.py
```

Matches across **11 inference services**, **the standalone lib itself**,
**`ai4icore_service_base`** (which loads it in its inference factory), the
**compose file**, and the lib's own tests/README. No other service touches it.

```
$ grep -rEn "^\s*(from|import)\s+ai4icore_service_base" services/ --include='*.py'
# → 24 hits across 11 inference services + pipeline-service.
# No other service imports ai4icore_service_base at all.
```
