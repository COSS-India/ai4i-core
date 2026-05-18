# `ai4icore_exceptions` — Usage Analysis

**Status:** Factual map of who uses the lib (direct and transitive) and who doesn't.
**Generated:** 2026-05-15

---

## TL;DR

`ai4icore_exceptions` is the **most heavily-used shared library in the
platform**. It owns the canonical exception hierarchy, the JSON response
envelope, and the FastAPI exception handlers.

**Direct consumers in `services/`:** 18 services import it in Python source.

```
asr-service, audio-lang-detection-service, language-detection-service,
language-diarization-service, llm-service, ner-service, nmt-service,
ocr-service, speaker-diarization-service, transliteration-service, tts-service,
auth-service, platform-core-service, pipeline-service,
alert-management-service, telemetry-service, policy-service, pii-service
```

**Indirect consumers via other shared libs:**

```
ai4icore_bootstrap.factory          → register_exception_handlers
ai4icore_service_base.app_factory   → register_exception_handlers
ai4icore_service_base.rate_limit    → RateLimitExceededError
ai4icore_model_management.middleware       → UnpublishedServiceError
ai4icore_model_management.triton_client    → TritonInferenceError
ai4icore_constants.{exceptions,responses,exception_handlers}  → compat-shim re-exports (unused by anyone today)
```

**Zero-footprint services** (no import, no Dockerfile install, no compose
mount): the API gateways (nginx-only), `auth-service-v2`,
`model-management-service`, `pay-per-use-service`, `policy-engine`,
`multi-tenant-feature`, `alert-config-sync-service`, `alerting-service`,
`dashboard-service`, `docs-manager`, `metrics-service`, `request-profiler`,
`smr-service`. These services either don't expose a Python HTTP surface
(gateways, `config-service`) or have their own exception layers and don't
participate in the platform's shared exception envelope.

---

## 1. What the lib provides

Source: [libs/ai4icore_exceptions/ai4icore_exceptions/](../libs/ai4icore_exceptions/ai4icore_exceptions/)

| Module | LOC | Public surface | Purpose |
|---|---:|---|---|
| `exceptions.py` | 329 | ~30 exception classes (`AppError` base + auth/authz/resource/validation/tenant/rate-limit/service/pipeline categories), plus `ErrorDetail` and `ErrorResponse` pydantic models | The canonical hierarchy. Every service raises subclasses of these. |
| `handlers.py` | 400 | `register_exception_handlers(app)` | Registers FastAPI exception handlers that turn raised `AppError` subclasses into RFC-compliant JSON error envelopes with correct status codes. |
| `responses.py` | 26 | `success_response`, `error_response` | Helpers that produce the platform-standard `{status, code, message, data}` JSON envelope used in every route response. |
| `__init__.py` | 114 | Re-exports everything above + a wide `__all__` | Single import surface (`from ai4icore_exceptions import …`). |
| **Total** | **869** | | |

Dependencies declared in [libs/ai4icore_exceptions/pyproject.toml](../libs/ai4icore_exceptions/pyproject.toml):

```
fastapi >= 0.104.0
pydantic >= 2.0.0
```

This is a FastAPI-coupled lib by design — the handler module wires
exceptions into FastAPI's error-response pipeline.

---

## 2. Who consumes it

### 2.1 Direct imports in services (Python source)

Eighteen services import `ai4icore_exceptions` from their own code. The
imports cluster around three patterns:

1. **`app/core/exceptions.py`** — a thin per-service shim that
   `from ai4icore_exceptions import (...)` and re-exports the symbols the
   service uses. Every service that has this pattern does it identically.
2. **`app/core/responses.py`** — `from ai4icore_exceptions import success_response, error_response` for the JSON envelope helpers used by every route.
3. **`app/services/*.py`** and **`app/clients/triton_client.py`** — raise
   specific exception classes directly: `TritonInferenceError`,
   `AudioProcessingError`, `InsufficientPermissionsError`, `ErrorDetail`, etc.

| Service | # Python files importing | Key symbols used |
|---|:---:|---|
| `asr-service` | 5 | `AppError` family, `TritonInferenceError`, `AudioProcessingError`, `ErrorDetail`, `success_response`, `error_response` |
| `audio-lang-detection-service` | 4 | `TritonInferenceError`, full `AppError` re-export, envelopes |
| `language-detection-service` | 3 | `TritonInferenceError`, full `AppError` re-export, envelopes |
| `language-diarization-service` | 4 | `TritonInferenceError`, full `AppError` re-export, envelopes |
| `llm-service` | 4 | `TritonInferenceError`, full `AppError` re-export, envelopes |
| `ner-service` | 3 | `AppError` family, envelopes |
| `nmt-service` | 3 | `AppError` family, envelopes |
| `ocr-service` | 4 | `TritonInferenceError`, `AppError` family, envelopes |
| `speaker-diarization-service` | 4 | `TritonInferenceError`, `AppError` family, envelopes |
| `transliteration-service` | 3 | `AppError` family, envelopes |
| `tts-service` | 3 | `AppError` family, envelopes |
| `auth-service` | 3 | Full auth-flavoured `AppError` set (`TokenExpiredError`, `InvalidCredentialsError`, `InsufficientPermissionsError`, …), envelopes |
| `pipeline-service` | 3 | `AppError`, `register_exception_handlers`, envelopes |
| `platform-core-service` | 2 | `AppError` family, envelopes |
| `alert-management-service` | 2 | `register_exception_handlers`, `InsufficientPermissionsError` |
| `telemetry-service` | 1 | `register_exception_handlers` |
| `policy-service` | 1 | `register_exception_handlers` |
| `pii-service` | 1 | `register_exception_handlers` |

Total: **63 import lines across 51 files in 18 services.**

### 2.2 Indirect — via four other shared libs

`ai4icore_exceptions` is also depended on by other libs in `libs/`, which
means many services pick it up transitively even if they didn't import it
directly:

| Consumer lib | File | Symbols imported |
|---|---|---|
| `ai4icore_bootstrap` | [libs/ai4icore_bootstrap/ai4icore_bootstrap/factory.py:92](../libs/ai4icore_bootstrap/ai4icore_bootstrap/factory.py#L92) | `register_exception_handlers` |
| `ai4icore_service_base` | [libs/ai4icore_service_base/ai4icore_service_base/app_factory.py:41](../libs/ai4icore_service_base/ai4icore_service_base/app_factory.py#L41) | `register_exception_handlers` |
| `ai4icore_service_base` | [libs/ai4icore_service_base/ai4icore_service_base/rate_limit.py:23](../libs/ai4icore_service_base/ai4icore_service_base/rate_limit.py#L23) | `RateLimitExceededError` |
| `ai4icore_model_management` | [libs/ai4icore_model_management/ai4icore_model_management/middleware.py:35](../libs/ai4icore_model_management/ai4icore_model_management/middleware.py#L35) | `UnpublishedServiceError` |
| `ai4icore_model_management` | [libs/ai4icore_model_management/ai4icore_model_management/triton_client.py:31](../libs/ai4icore_model_management/ai4icore_model_management/triton_client.py#L31) | `TritonInferenceError` |
| `ai4icore_constants` (compat shims) | [exception_handlers.py:10](../libs/ai4icore_constants/ai4icore_constants/exception_handlers.py#L10), [exceptions.py:12-13](../libs/ai4icore_constants/ai4icore_constants/exceptions.py#L12), [responses.py:10](../libs/ai4icore_constants/ai4icore_constants/responses.py#L10) | full re-export. *Nothing in the repo imports through these shim paths today — see the constants doc.* |

Practical implication: every service that calls
`create_inference_app(...)` from `ai4icore_service_base` (the 11
inference services) **and** `pipeline-service` (which uses
`ai4icore_service_base` for `RateLimitMiddleware` /
`ServiceRegistryClient`) pulls in `ai4icore_exceptions` via the lib
chain, in addition to their direct imports.

### 2.3 Compose / Dockerfile bindings (operational, not code)

* **Dockerfile (build time):** **19 services** `COPY libs/ai4icore_exceptions` + `pip install -e .`:

  ```
  alert-management-service, asr-service, audio-lang-detection-service,
  auth-service, config-service, language-detection-service,
  language-diarization-service, llm-service, ner-service, nmt-service,
  ocr-service, pii-service, pipeline-service, platform-core-service,
  policy-service, speaker-diarization-service, telemetry-service,
  transliteration-service, tts-service
  ```

  `config-service` installs the lib in its image even though its
  (Python-less) surface doesn't import from it.

* **docker-compose-local.yml (dev hot-reload):** **16 service blocks**
  bind-mount `./libs/ai4icore_exceptions:/...`:

  ```
  alert-management-service, asr-service, audio-lang-detection-service,
  auth-service, language-detection-service, language-diarization-service,
  llm-service, ner-service, nmt-service, ocr-service, pipeline-service,
  platform-core-service, speaker-diarization-service, telemetry-service,
  transliteration-service, tts-service
  ```

---

## 3. Who does **not** use it

Services with **zero** footprint — no Python import, no Dockerfile
install, no compose bind-mount:

| Service | Why it doesn't use it |
|---|---|
| `api-gateway-service` | nginx-only; no Python surface. |
| `api-gateway-legacy` | nginx-only. |
| `auth-service-v2` | Legacy / decommissioned (see recent commit `2deee548 chore(auth): decommission auth-service-v2`). |
| `model-management-service` | Has its own local middleware at `services/model-management-service/middleware/error_handler_middleware.py` — predates the shared lib. |
| `pay-per-use-service` | Doesn't expose user-facing HTTP error envelopes from the shared hierarchy. |
| `policy-engine` | Internal evaluator service, no FastAPI surface that uses the envelope. |
| `multi-tenant-feature` | Legacy feature flag service; uses its own error middleware. |
| `alert-config-sync-service` | Background sync, no public HTTP endpoints. |
| `alerting-service` | Background alerter. |
| `dashboard-service` | Standalone dashboard process. |
| `docs-manager` | Static docs manager. |
| `metrics-service` | Background metrics aggregator. |
| `request-profiler` | Profiling/standalone tooling. |
| `smr-service` | SMR worker. |

These services either bypass the platform JSON envelope (using their own
ad-hoc error responses) or expose no HTTP error surface in the first place.

### Outliers worth knowing about

* **`config-service`** installs the lib in its Dockerfile but its code
  doesn't import from it. Stale Dockerfile layer.
* **`model-management-service`** is interesting — it *owns* the
  `ServiceUnavailableError` / `ModelNotFoundError` / `UnpublishedServiceError`
  semantics that the rest of the platform consumes via the shared lib, but
  it itself does not use the shared lib. It ships its own hand-written
  FastAPI exception handler at
  `services/model-management-service/middleware/error_handler_middleware.py`.

**Reproducible verification:**

```bash
# Every service that imports the standalone lib
grep -rln "ai4icore_exceptions" services/ --include='*.py' | awk -F/ '{print $2}' | sort -u

# Every lib (other than the lib itself) that imports it
grep -rEln "^\s*(from|import)\s+ai4icore_exceptions" libs/ --include='*.py' | grep -v '/ai4icore_exceptions/'

# Every service that mounts it in compose
awk '/^  [a-z][a-z0-9-]+(-service|-v2|-legacy|-engine|-sync-service|-profiler|-manager|-feature):/{svc=$1} /ai4icore_exceptions/{print svc}' docker-compose-local.yml | sort -u
```

---

## 4. What the lib depends on

```
fastapi >= 0.104.0
pydantic >= 2.0.0
```

That's it. Both are baseline requirements for every FastAPI service in
the platform — `ai4icore_exceptions` adds no new transitive weight
beyond what every service already has.

---

## 5. Observations

1. **This is the most-load-bearing shared lib in the repo.** Eighteen
   services import it directly, four other libs depend on it transitively,
   and the JSON-envelope helpers (`success_response`, `error_response`)
   are the platform's canonical response shape. Changing the public API of
   `ai4icore_exceptions` is a platform-wide breaking change.
2. **Almost every service that exposes user-facing HTTP error responses
   uses it.** The notable exception is `model-management-service`, which
   defines the *meaning* of several exceptions the rest of the platform
   raises (e.g. `UnpublishedServiceError` for an inactive service) but
   doesn't itself use the shared envelope — it has a parallel
   hand-rolled error middleware. That's a small inconsistency in the
   platform.
3. **The `ai4icore_constants` compat shims** are forwarders to this lib's
   public API. Nothing in the repo imports them today (see the constants
   doc for details).
4. **No "lazy-import escape hatch" is needed.** Unlike
   `ai4icore_model_management` (which is inference-only and is therefore
   gated behind a `__getattr__` in `ai4icore_service_base/__init__.py`),
   `ai4icore_exceptions` is a base requirement of `ai4icore_service_base`
   itself — every consumer of `service_base` ends up with it.

---

## 6. Appendix — quick-reference grep results

```
$ git grep -lE "^\s*(from|import)\s+ai4icore_exceptions" \
    -- 'services/**.py' 'libs/**.py' ':!libs/ai4icore_exceptions/**'
libs/ai4icore_bootstrap/ai4icore_bootstrap/factory.py
libs/ai4icore_constants/ai4icore_constants/exception_handlers.py
libs/ai4icore_constants/ai4icore_constants/exceptions.py
libs/ai4icore_constants/ai4icore_constants/responses.py
libs/ai4icore_model_management/ai4icore_model_management/middleware.py
libs/ai4icore_model_management/ai4icore_model_management/triton_client.py
libs/ai4icore_service_base/ai4icore_service_base/app_factory.py
libs/ai4icore_service_base/ai4icore_service_base/rate_limit.py
services/alert-management-service/main.py
services/alert-management-service/utils/auth_deps.py
services/asr-service/app/clients/triton_client.py
services/asr-service/app/core/exceptions.py
services/asr-service/app/core/responses.py
services/asr-service/app/dependencies/services.py
services/asr-service/app/services/asr_service.py
services/audio-lang-detection-service/app/clients/triton_client.py
services/audio-lang-detection-service/app/core/exceptions.py
services/audio-lang-detection-service/app/core/responses.py
services/audio-lang-detection-service/app/services/audio_lang_detection_service.py
services/auth-service/app/core/exceptions.py
services/auth-service/app/core/jwt_verifier.py
services/auth-service/app/core/responses.py
services/language-detection-service/app/core/exceptions.py
services/language-detection-service/app/core/responses.py
services/language-detection-service/app/services/language_detection_service.py
services/language-diarization-service/app/clients/triton_client.py
services/language-diarization-service/app/core/exceptions.py
services/language-diarization-service/app/core/responses.py
services/language-diarization-service/app/services/language_diarization_service.py
services/llm-service/app/clients/triton_client.py
services/llm-service/app/core/exceptions.py
services/llm-service/app/core/responses.py
services/llm-service/app/services/llm_service.py
services/ner-service/app/core/exceptions.py
services/ner-service/app/core/responses.py
services/ner-service/app/services/ner_service.py
services/nmt-service/app/core/exceptions.py
services/nmt-service/app/core/responses.py
services/nmt-service/app/services/nmt_service.py
services/ocr-service/app/clients/triton_client.py
services/ocr-service/app/core/exceptions.py
services/ocr-service/app/core/responses.py
services/ocr-service/app/services/ocr_service.py
services/pii-service/main.py
services/pipeline-service/app/core/exceptions.py
services/pipeline-service/app/core/responses.py
services/pipeline-service/app/main.py
services/platform-core-service/app/core/exceptions.py
services/platform-core-service/app/core/responses.py
services/policy-service/app/main.py
services/speaker-diarization-service/app/clients/triton_client.py
services/speaker-diarization-service/app/core/exceptions.py
services/speaker-diarization-service/app/core/responses.py
services/speaker-diarization-service/app/services/speaker_diarization_service.py
services/telemetry-service/main.py
services/transliteration-service/app/core/exceptions.py
services/transliteration-service/app/core/responses.py
services/transliteration-service/app/services/transliteration_service.py
services/tts-service/app/core/exceptions.py
services/tts-service/app/core/responses.py
services/tts-service/app/services/tts_service.py
```

51 files in 18 services + 5 internal lib files. By a wide margin the
most-imported shared lib in the platform.
