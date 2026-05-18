# `ai4icore_core.constants` — Usage Analysis

**Status:** Factual map of who imports `ai4icore_core.constants` (the
constants subpackage shipped inside the `ai4icore-core` PyPI package).
**Generated:** 2026-05-15

> Scope note: this doc covers `from ai4icore_core.constants import …`
> only. The constants subpackage is now sourced via the consolidated
> `ai4icore-core` PyPI package — the standalone `libs/ai4icore_constants/`
> path is not what services consume.

---

## TL;DR

`ai4icore_core.constants` is consumed by **5 services, across 12 Python
import lines**:

```
asr-service            (3 import lines, all from .error_messages)
nmt-service            (3 import lines, all from .error_messages)
tts-service            (2 import lines, all from .error_messages)
transliteration-service (1 import line,  from .error_messages)
pipeline-service       (3 import lines, all from .exceptions — the backward-compat shim)
```

Almost all real usage targets a single submodule: **`ai4icore_core.constants.error_messages`** — services pull canonical error-code/message string constants (`SERVICE_UNAVAILABLE`, `SERVICE_UNPUBLISHED`, `MODEL_UNAVAILABLE`, `INVALID_REQUEST`, etc.) for use in their JSON error envelopes.

The other submodules:

| Submodule | Status |
|---|---|
| `ai4icore_core.constants.error_messages` | **9 import lines** across 4 services (asr, nmt, tts, transliteration). |
| `ai4icore_core.constants.exceptions` (compat shim → `ai4icore_core.exceptions.exceptions`) | **3 import lines**, all in `pipeline-service`. |
| `ai4icore_core.constants.responses` (compat shim) | **0 imports** anywhere. |
| `ai4icore_core.constants.exception_handlers` (compat shim) | **0 imports** anywhere. |
| Root namespace (`from ai4icore_core.constants import …` / `import ai4icore_core.constants`) | **0 imports** — the `SERVICE_TO_RESOURCE_MAP` dict and `get_resource_name()` helper exposed at the package root are unused. |

No code in `libs/` (other than the subpackage's own internal files)
imports from `ai4icore_core.constants`. Every consumer is in `services/`.

---

## 1. What the subpackage provides

Source: [libs/ai4icore_core/ai4icore_core/constants/](../libs/ai4icore_core/ai4icore_core/constants/)

| Module | LOC | Public surface | Purpose |
|---|---:|---|---|
| `error_messages.py` | 148 | ~80 string constants (`SERVICE_UNAVAILABLE`, `SERVICE_UNPUBLISHED`, `MODEL_UNAVAILABLE`, `RATE_LIMIT_EXCEEDED`, `INVALID_REQUEST`, …) plus their human-facing `_MESSAGE` counterparts. | Canonical error-code and -message strings. Pure static data, no behavior. |
| `__init__.py` | 19 | `from .error_messages import *`, `SERVICE_TO_RESOURCE_MAP` dict, `get_resource_name(service_name)` helper. | Service-name → resource-name normalization (hyphens → underscores). The wildcard re-export means `from ai4icore_core.constants import SERVICE_UNAVAILABLE` would work, but in practice everyone imports through `.error_messages` explicitly. |
| `exceptions.py` | 20 | Backward-compat shim: `try: from ai4icore_core.exceptions.exceptions import *`. | Lets old-style `from ai4icore_constants.exceptions import …` patterns keep working under the consolidated namespace. Used by `pipeline-service` only. |
| `responses.py` | 18 | Backward-compat shim → `ai4icore_core.exceptions.responses` (`success_response`, `error_response`). | Unused. |
| `exception_handlers.py` | 18 | Backward-compat shim → `ai4icore_core.exceptions.handlers` (`register_exception_handlers`). | Unused. |
| **Total** | **223** | | |

The subpackage docstring is explicit about its role:

```text
NO behavior, NO exceptions, NO FastAPI dependency.
Exceptions live in ai4icore_exceptions.
```

— i.e., `.error_messages` is the canonical content; the three
`exceptions` / `responses` / `exception_handlers` modules exist only as
backward-compat forwarders to the exceptions subpackage.

---

## 2. Who consumes it

### 2.1 Per-service direct imports

| Service | File | Imported from | Symbols |
|---|---|---|---|
| `asr-service` | [`app/dependencies/services.py:8`](../services/asr-service/app/dependencies/services.py#L8) | `.error_messages` | `MODEL_UNAVAILABLE`, `MODEL_UNAVAILABLE_MESSAGE`, `INVALID_REQUEST`, `INVALID_REQUEST_MESSAGE` |
| `asr-service` | [`app/routes/inference.py:8`](../services/asr-service/app/routes/inference.py#L8) | `.error_messages` | `SERVICE_UNAVAILABLE`, `SERVICE_UNAVAILABLE_MESSAGE` |
| `asr-service` | [`app/services/smr_service.py:17`](../services/asr-service/app/services/smr_service.py#L17) | `.error_messages` | `SERVICE_UNPUBLISHED`, `SERVICE_UNPUBLISHED_MESSAGE` |
| `nmt-service` | [`app/routes/inference.py:8`](../services/nmt-service/app/routes/inference.py#L8) | `.error_messages` | `SERVICE_UNAVAILABLE` |
| `nmt-service` | [`app/routes/try_it.py:12`](../services/nmt-service/app/routes/try_it.py#L12) | `.error_messages` | `SERVICE_UNPUBLISHED`, `SERVICE_UNPUBLISHED_MESSAGE` |
| `nmt-service` | [`app/services/smr_service.py:17`](../services/nmt-service/app/services/smr_service.py#L17) | `.error_messages` | `SERVICE_UNPUBLISHED`, `SERVICE_UNPUBLISHED_MESSAGE` |
| `tts-service` | [`app/routes/inference.py:8`](../services/tts-service/app/routes/inference.py#L8) | `.error_messages` | `SERVICE_UNAVAILABLE` |
| `tts-service` | [`app/services/smr_service.py:17`](../services/tts-service/app/services/smr_service.py#L17) | `.error_messages` | `SERVICE_UNPUBLISHED`, `SERVICE_UNPUBLISHED_MESSAGE` |
| `transliteration-service` | [`app/routes/inference.py:8`](../services/transliteration-service/app/routes/inference.py#L8) | `.error_messages` | `SERVICE_UNAVAILABLE`, `SERVICE_UNAVAILABLE_MESSAGE` |
| `pipeline-service` | [`app/routes/pipeline.py:16`](../services/pipeline-service/app/routes/pipeline.py#L16) | `.exceptions` (compat shim) | `PipelineError`, `PipelineTaskError`, `ServiceUnavailableError`, `ModelNotFoundError`, `ErrorDetail`, `AuthenticationError` |
| `pipeline-service` | [`app/services/pipeline_service.py:16`](../services/pipeline-service/app/services/pipeline_service.py#L16) | `.exceptions` (compat shim) | `PipelineTaskError`, `ServiceUnavailableError`, `ModelNotFoundError`, `AuthenticationError` |
| `pipeline-service` | [`app/clients/http_client.py:319`](../services/pipeline-service/app/clients/http_client.py#L319) | `.exceptions` (compat shim) — *inline import inside a function* | `AuthenticationError` |

### 2.2 Aggregate view

| Service | Files | Import lines | Submodules touched |
|---|:---:|:---:|---|
| `asr-service` | 3 | 3 | `error_messages` |
| `nmt-service` | 3 | 3 | `error_messages` |
| `tts-service` | 2 | 2 | `error_messages` |
| `transliteration-service` | 1 | 1 | `error_messages` |
| `pipeline-service` | 3 | 3 | `exceptions` (compat shim) |
| **Total** | **12** | **12** | `error_messages` + `exceptions` |

### 2.3 No transitive consumers via other shared libs

A grep across `libs/` for `from ai4icore_core.constants` returns **only
internal mirrors** inside the consolidated package itself
([libs/ai4icore_core/ai4icore_core/constants/exceptions.py:12](../libs/ai4icore_core/ai4icore_core/constants/exceptions.py#L12),
[constants/responses.py:10](../libs/ai4icore_core/ai4icore_core/constants/responses.py#L10),
[constants/exception_handlers.py:10](../libs/ai4icore_core/ai4icore_core/constants/exception_handlers.py#L10))
— no other shared lib in `libs/` (`ai4icore_bootstrap`,
`ai4icore_service_base`, `ai4icore_model_management`,
`ai4icore_logging`, etc.) imports from `ai4icore_core.constants`. So
every consumer of the subpackage is direct, in a service.

### 2.4 How services get the subpackage

The subpackage ships inside the **`ai4icore-core` PyPI package** —
services obtain it via `requirements.txt`:

```
# requirements.txt of each consumer
ai4icore-core>=1.0.0
```

Confirmed in all 5 consumer services
([asr](../services/asr-service/requirements.txt),
[nmt](../services/nmt-service/requirements.txt),
[tts](../services/tts-service/requirements.txt),
[transliteration](../services/transliteration-service/requirements.txt),
[pipeline](../services/pipeline-service/requirements.txt)).

There are no per-service Dockerfile `COPY libs/ai4icore_core` layers and
no per-service compose bind-mounts of `ai4icore_core` — installation
goes through `pip install -r requirements.txt` against PyPI like any
other third-party dependency.

---

## 3. Who does **not** use it

Every other service in the repo, regardless of whether they pip-install
`ai4icore-core` for other subpackages (e.g. `ai4icore_core.email`,
`ai4icore_core.bootstrap`, `ai4icore_core.service_base`, etc.), does
**not** import from `ai4icore_core.constants`:

| Service | Has `ai4icore-core` in requirements? | Imports from `ai4icore_core.constants`? |
|---|:---:|:---:|
| `auth-service` | ✓ | ✗ |
| `platform-core-service` | ✓ | ✗ |
| `audio-lang-detection-service` | ✓ | ✗ |
| `language-detection-service` | ✓ | ✗ |
| `language-diarization-service` | ✓ | ✗ |
| `llm-service` | ✓ | ✗ |
| `ner-service` | ✓ | ✗ |
| `ocr-service` | ✓ | ✗ |
| `speaker-diarization-service` | ✓ | ✗ |
| `model-management-service` | ✗ | ✗ |
| `policy-service` | ✗ | ✗ |
| `policy-engine` | ✗ | ✗ |
| `pii-service` | ✗ | ✗ |
| `telemetry-service` | ✗ | ✗ |
| `metrics-service` | ✗ | ✗ |
| `smr-service` | ✗ | ✗ |
| `alert-management-service` | ✗ | ✗ |
| `alert-config-sync-service` | ✗ | ✗ |
| `alerting-service` | ✗ | ✗ |
| `dashboard-service` | ✗ | ✗ |
| `docs-manager` | ✗ | ✗ |
| `request-profiler` | ✗ | ✗ |
| `pay-per-use-service` | ✗ | ✗ |
| `multi-tenant-feature` | ✗ | ✗ |
| `auth-service-v2` | ✗ | ✗ |
| `config-service` | n/a (not Python) | ✗ |
| `api-gateway-service` | n/a (nginx) | ✗ |
| `api-gateway-legacy` | n/a | ✗ |

**Reproducible verification:**

```bash
# Distinct services importing ai4icore_core.constants
grep -rln "ai4icore_core\.constants" services/ --include='*.py' | awk -F/ '{print $2}' | sort -u

# Per-submodule import counts
for sub in error_messages exceptions responses exception_handlers; do
  cnt=$(grep -rcE "ai4icore_core\.constants\.$sub" services/ --include='*.py' | awk -F: '{s+=$2} END {print s+0}')
  echo "ai4icore_core.constants.$sub  -> $cnt"
done

# Root-namespace imports (none expected)
grep -rEn "^\s*(from\s+ai4icore_core\.constants\s+import|import\s+ai4icore_core\.constants\b)" \
  services/ libs/ --include='*.py'
```

---

## 4. What the subpackage depends on

The subpackage itself has no extra runtime dependencies of its own — it
ships inside `ai4icore-core` whose `pyproject.toml` declares the
broader package's deps. The data file `error_messages.py` has zero
imports. The three compat-shim files transitively pull
`ai4icore_core.exceptions` (a peer subpackage in the same wheel) when
they're imported, which only matters for `pipeline-service` since it's
the only consumer of the `.exceptions` shim.

---

## 5. Observations

1. **The active surface area is exactly one file: `error_messages.py`.**
   Four of the five consumer services use only that submodule, and they
   pull 4 specific name pairs out of it (`SERVICE_UNAVAILABLE` /
   `SERVICE_UNAVAILABLE_MESSAGE`, `SERVICE_UNPUBLISHED` /
   `SERVICE_UNPUBLISHED_MESSAGE`, `MODEL_UNAVAILABLE` /
   `MODEL_UNAVAILABLE_MESSAGE`, `INVALID_REQUEST` /
   `INVALID_REQUEST_MESSAGE`). The rest of the ~80 constants in
   `error_messages.py` are present but unused.
2. **Only `pipeline-service` touches the `.exceptions` compat shim.** It
   imports `PipelineError`, `PipelineTaskError`,
   `ServiceUnavailableError`, `ModelNotFoundError`, `ErrorDetail`,
   `AuthenticationError` — these classes actually live in
   `ai4icore_core.exceptions`; the `.constants.exceptions` shim is a
   thin re-export. Pipeline-service is the only place this forwarding
   path is in use.
3. **The `.responses` and `.exception_handlers` compat shims are dead.**
   No service or other lib imports them.
4. **The root namespace is unused too.** Despite `__init__.py` exposing
   the constants via `from .error_messages import *` plus
   `SERVICE_TO_RESOURCE_MAP` and `get_resource_name()`, no code does
   `from ai4icore_core.constants import SERVICE_UNAVAILABLE` or
   `from ai4icore_core.constants import SERVICE_TO_RESOURCE_MAP` — every
   import explicitly names a submodule.

---

## 6. Appendix — quick-reference grep results

```
$ git grep -lE "^\s*(from|import)\s+ai4icore_core\.constants" \
    -- 'services/**.py' 'libs/**.py' ':!libs/ai4icore_core/ai4icore_core/constants/**'
services/asr-service/app/dependencies/services.py
services/asr-service/app/routes/inference.py
services/asr-service/app/services/smr_service.py
services/nmt-service/app/routes/inference.py
services/nmt-service/app/routes/try_it.py
services/nmt-service/app/services/smr_service.py
services/pipeline-service/app/clients/http_client.py
services/pipeline-service/app/routes/pipeline.py
services/pipeline-service/app/services/pipeline_service.py
services/transliteration-service/app/routes/inference.py
services/tts-service/app/routes/inference.py
services/tts-service/app/services/smr_service.py
```

12 files in 5 services. Zero matches outside `services/` (i.e., no
other shared lib in `libs/` imports `ai4icore_core.constants`).

```
$ git grep -lE "^\s*(from|import)\s+ai4icore_core\.constants" -- 'libs/**.py' \
    | grep -v 'libs/ai4icore_core/ai4icore_core/constants/'
# → empty
```
