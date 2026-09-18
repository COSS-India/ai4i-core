# AI4IDS-3146 — Authentication Token for vLLM Model Endpoints

Status: implemented (see §8 for how the final design differs from the
original draft below, discovered while building it)
Jira: https://coss-team-ai4x.atlassian.net/browse/AI4IDS-3146

## 1. Problem statement

Create/Update Service (LLM task type) needs an optional authentication token that
AI4I Orchestrator sends as `Authorization: Bearer <token>` when calling a vLLM
endpoint hosted with `--api-key`/`VLLM_API_KEY`. Token must be optional, stored
securely, never appear in logs/traces/errors/API responses, and not affect
existing services.

## 2. Current state (verified by reading the code, not comments)

### 2.1 Storage — `mm_services` (platform-core-service)

`app/models/model_management/service.py`:
- `api_key: String(255)` — deprecated flat column, **plaintext**.
- `inference_api_key: JSONB` — canonical `{name, value}` shape, **plaintext**.

Both are generic "auth header for this service's endpoint" fields, not
LLM-specific. Write path: `app/services/model-management/service_service.py`
`create_service` (L314-315) / `update_service` (L458-466) assign both verbatim
from the request, no encryption.

Schema: `InferenceApiKey` (`app/schemas/common.py:188-197`) —
`{name: str = "Authorization", value: str}`. Exposed on
`InferenceAPIEndPoint.inferenceApiKey` (`app/schemas/model_management/service.py:166-168`).

### 2.2 Response masking is inconsistent between the two columns

`app/services/model-management/serializers.py`:
- `inferenceEndPoint.inferenceApiKey.value` is **always** masked to `"***"`
  via `_mask_api_key()` (L79-88, L39-42) — for every caller, admin included.
- The deprecated flat `"api_key"` field (L147) is **deliberately left
  unmasked**, with a comment explaining inference-service reads this exact
  key off this exact response to build the Triton `Authorization` header.

Net effect: `inference_api_key` (JSONB, "canonical") is **never actually
consumed at inference time by anything today** — only the deprecated flat
`api_key` reaches Triton. The canonical field is write-only.

### 2.3 RBAC filtering strips both fields for inference-service's own call

`app/routes/service.py`:
- `GET /services/{id}` (`view_service`, L220-233) and `GET /services`
  (`list_services`, L154-211) call `_filter_service_fields()` (L108-111)
  whenever `_is_platform_admin(request)` (L104-105) is false — i.e. no
  `X-Permission-IDS` header for role 1 (admin) or 2 (moderator).
  `_NON_ADMIN_SERVICE_FIELDS` (L70-94) does not include `api_key` or
  `inferenceEndPoint`.
- Added in commit `79f301d5` (AI4IDS-1816, 2026-07-21). Before that commit the
  full dict was returned unconditionally.

### 2.4 inference-service never sends identity headers on this call

`services/inference-service/inference/inference_server_resolver.py:77-78`
calls `GET {MODEL_MANAGEMENT_SERVICE_URL}/api/v1/services/{id}` via
`HTTPServiceClient.get_json(url)` — no headers argument, and
`utils/http_client.py:24-59` adds no default headers anywhere. There is no
other internal/service-to-service route; `app/routes/internal.py` has exactly
one unrelated endpoint (`POST /internal/ppu/billing-cycle-reset`), and it is
protected only by not being exposed through APISIX — `include_in_schema=False`
hides it from OpenAPI docs, it performs **no auth check in code**.

**Consequence (confirmed live regression, independent of this story):**
`_is_platform_admin()` is always false for this call →
`_filter_service_fields()` strips `api_key` → `_normalize_mms_response()`
(L161-162: `data.get("apiKey") or data.get("api_key")`) always resolves to
`None` → `services/inference-service/services/base/task_service.py:407-410`
(`if api_key: headers["Authorization"] = f"Bearer {api_key}"`) never fires.
**Every Triton call has gone out with no Authorization header since
2026-07-21**, silently, with no log or error. Git history confirms this
predates the fix and was never reconciled.

Per product decision, **fixing this is in scope for AI4IDS-3146** (see §4.1) —
building the new vLLM auth feature on top of the same broken channel would
just reproduce the same silent failure for vLLM too.

### 2.5 LLM proxy never attaches any auth header today

`services/inference-service/services/llm_service.py`
(`OpenAIProxyService`) — three independent outbound call sites, no shared
header-building helper:
- `forward()` (buffered, L114-132) — `headers={"Content-Type": "application/json"}`.
- `open_stream()` (SSE, L349-388) — same, via `client.build_request(...)` (L368-371).
- `proxy_multipart()` (audio passthrough, L552-639) — no headers dict at all.

None read `service_info["api_key"]` or any token. `service_info` comes from
`InferenceServerResolver.resolve_service()` (module-level singleton,
per-process in-memory TTL cache, `CACHE_TTL_SECONDS` default 300s — not
shared across pods, not invalidated centrally).

### 2.6 Logging/tracing discipline (good news — mostly already safe)

- `inference_server_resolver.py:80-87` explicitly avoids logging the full
  `service_info` dict "because it contains the resolved Triton endpoint URL
  and api_key" — logs only `service_id`/`name`.
- `llm_service.py:302,441` log URL + service_id only, never headers/payload.
- OTel spans (`trace/request_span.py`) carry only structured attrs
  (userId, tenantId, model_name, service_id, ...), never raw headers/bodies.
- Existing regression test `test_triton_url_redaction.py` (AI4IDS-1871) pins
  this for Triton URLs/keys — needs an equivalent for the vLLM token (§7).

### 2.7 No encryption-at-rest exists for this class of secret

- No shared crypto utility in `libs/`. auth-service has
  `app/core/pii_crypto.py` (AES-**SIV**, deterministic, keyed by
  `PII_ENCRYPTION_KEY`) + `EncryptedString`/`EncryptedEmail`/`EncryptedPhone`
  `TypeDecorator`s (`app/models/types.py`) — deterministic **on purpose**, so
  `User.email == value` still works as an equality lookup. A bearer token
  never needs equality search, so copying AES-SIV as-is would be strictly
  worse than necessary (same plaintext twice → identical ciphertext).
- `platform-core-service/app/core/config.py`'s `CoreSettings` has no
  `*_ENCRYPTION_KEY`/`*_SECRET` field today — would be new, following the
  existing plain `Optional[str]` settings pattern.
- No live Vault/Secrets-Manager/K8s-Secret integration exists in code
  anywhere in the repo (`VAULT_ADDR`/`VAULT_TOKEN` in `.env` are unused
  placeholders, zero `hvac` references).
- The only other real precedent, `mm_services.api_key`/`inference_api_key`,
  is plaintext — not a pattern to copy, a gap to not repeat.

## 3. Design decisions

### 3.1 Reuse `inferenceEndPoint.inferenceApiKey`, do not add a new column

The `{name, value}` JSONB field already exists end-to-end (schema, DTOs,
ORM, masked serialization) and — per §2.2/2.5 — is currently dead at
runtime for every task type. No migration is needed to add a column;
Postgres column type (`JSONB`) is unchanged, only its Python-side
(de)serialization changes (§3.3). This is additive: services with no token
keep resolving `inference_api_key: None`, so behavior is unchanged (AC #4, #7).

vLLM only supports the Bearer scheme (per the ticket's own vLLM docs
reference), so the LLM call sites always build
`Authorization: Bearer {value}` and ignore `name` for this task type — no
support for arbitrary header names is implemented, since nothing requires it.

**Open question for product/eng sign-off:** should setting
`inferenceApiKey` on a **non-LLM** service be a hard validation error ("only
for LLM TaskType" taken literally), or simply have no functional effect
(lenient — matches today's reality, where it's already inert for Triton)?
Recommend the lenient option to avoid any risk of rejecting an existing
stored value on an unrelated service during an update; happy to implement
either.

### 3.2 New internal, unfiltered resolution path (fixes §2.3/§2.4 + enables §2.5)

Add `GET /internal/services/{service_id}` to
`platform-core-service/app/routes/internal.py`:
- Returns the same shape as `view_service()` but **skips**
  `_filter_service_fields()` (this route is never reachable through APISIX,
  same trust boundary as the existing `/internal/ppu/billing-cycle-reset`
  cron endpoint) and passes `include_secrets=True` into `service_to_dict()`
  (new param, default `False`, skips `_mask_api_key()` for
  `inferenceApiKey` only when true — the flat legacy `api_key` is already
  unmasked in `service_to_dict()` regardless).
- **Defense in depth beyond network isolation**: this route returns
  plaintext secrets, a materially higher-value target than the existing cron
  trigger, so it should not rely solely on "not exposed via APISIX" (which
  is an external, unverifiable-from-this-repo assumption per the gateway
  memory). Add a shared-secret header check:
  `X-Internal-Service-Token` compared with `secrets.compare_digest()`
  against a new `INTERNAL_SERVICE_SHARED_SECRET` setting; 403 on
  missing/mismatch. inference-service sends the same value (new
  `MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN` env var) on every call.
- `inference_server_resolver.py._query_model_management_service()` switches
  its URL from `/api/v1/services/{id}` to `/internal/services/{id}` and adds
  the shared-secret header. `_normalize_mms_response()` gains one more
  extraction: `inference_api_key = (data.get("inferenceEndPoint") or {}).get("inferenceApiKey")`.

**Rollout risk to call out explicitly:** once this ships, Triton calls that
have had no Authorization header for ~2 months (§2.4) will start sending
one again for any service with a non-null `api_key`. If any of those stored
keys are stale/rotated on the Triton side, this flips from "no auth" to
"401" — recommend auditing existing `mm_services.api_key` values against
live Triton backends before/at rollout, not after.

### 3.3 Encryption at rest — new, scoped to `inference_api_key` only

- New `TypeDecorator` in platform-core-service wrapping the JSONB column:
  encrypts only the `value` sub-field on `process_bind_param`, decrypts on
  `process_result_value`. Deprecated flat `api_key` column is **left as-is,
  untouched** — no reason to retrofit encryption onto a column nothing new
  is built on.
- Algorithm: **AES-256-GCM** (randomized nonce per encryption), not AES-SIV
  — no equality search is ever needed on this value. Ciphertext stored as
  `enc:v1:<base64(nonce || ciphertext || tag)>`.
- Key: new `SERVICE_CREDENTIALS_ENCRYPTION_KEY` setting on
  `CoreSettings`, validated at startup (fail-fast on missing/malformed key,
  mirroring `pii_crypto.py`'s `validate_key()`).
- Backward-read compatibility: `process_result_value` treats any value
  without the `enc:v1:` prefix as legacy plaintext and returns it unchanged
  (values re-encrypt automatically on next write). No bulk backfill
  migration is required — the feature is unreleased, so no real vLLM tokens
  exist in the DB yet; a one-time backfill is a nice-to-have, not a blocker.

### 3.4 LLM proxy — attach the header at all three call sites

Factor out `_build_headers(service_info, *, content_type=None)` in
`llm_service.py`, used by `forward()`, `open_stream()`, and
`proxy_multipart()`: if `service_info.get("inference_api_key", {}).get("value")`
is present, add `Authorization: Bearer {value}`; otherwise unchanged from
today. One inline comment forbidding logging the return value, matching the
resolver's existing convention (§2.6).

## 4. API contract

No response shape changes. `inferenceEndPoint.inferenceApiKey.value` remains
`"***"` in every public-facing response (list, detail, non-admin filtered,
try-it) exactly as today — satisfies AC #5 for the API-response surface once
the internal endpoint (§3.2) is the only place secrets are ever returned
unmasked, and that path is gated by the shared-secret header, not by caller
role.

Create/Update Service request/response bodies are unchanged (same
`inferenceEndPoint.inferenceApiKey` field, same validation surface, plus the
open question in §3.1).

## 5. Testing plan (AC #8)

- Unit: `TypeDecorator` encrypt/decrypt round-trip; legacy-plaintext read
  compatibility; `_build_headers()` with/without token.
- Integration against the test vLLM endpoint from the Jira comment
  (`http://45.194.2.154:8300/v1/chat/completions`, `deepseek-r1-8b`,
  auth enabled) and one endpoint with no `--api-key` — both via a real
  Create Service → resolve → proxy call, not mocked.
- Regression: extend `test_triton_url_redaction.py`-style assertions to the
  LLM proxy path — sentinel token must never appear in logs or exception
  text.
- Manual: confirm existing Triton services still function after §3.2 ships,
  specifically the stale-key risk flagged there.

## 6. Open questions for product/eng sign-off

1. §3.1 — hard-reject `inferenceApiKey` on non-LLM services, or leave it
   inert (recommended)? **Resolved**: hard-reject, on the new dedicated
   field (see §8).
2. §3.2 rollout — who owns auditing existing `mm_services.api_key` values
   against live Triton backends before the internal-endpoint fix ships?
   **Still open** — not something this change can verify from the repo.

## 7. Testing performed

Full existing test suites for both services were run before and after this
change (`platform-core-service/tests/`, `inference-service/tests/`) to
diff the failure set — every pre-existing failure (missing `ai4i_core`/
`pytest-asyncio` in this sandbox, a handful of already-stale fixtures
unrelated to this story) reproduces identically on unmodified code; this
change introduces zero new failures. New coverage added:

- `test_service_credentials_crypto.py` — round-trip, randomized ciphertext
  (vs. PII's deterministic AES-SIV), legacy-plaintext read passthrough,
  key-validation fail-fast, and the base64-vs-hex decoding-ambiguity bug
  found and fixed while writing these tests (see §8).
- `test_service_ulca_alignment.py` — `authenticationToken` task-type gating
  on create/update, `mask_service_secrets()` behavior.
- `test_service_rbac_filtering.py` — admin no longer sees a real
  `api_key`/token value from the public route.
- `test_internal_service_resolution.py` — shared-secret gate (missing/
  wrong/matching token), unmasked response shape.
- `inference-service/tests/test_llm_service.py` — `_build_headers()` unit
  tests plus an end-to-end `forward()` test asserting the real outbound
  `httpx` call carries `Authorization: Bearer <token>`.

Not exercised: an actual vLLM endpoint (AC #8's with/without `--api-key`
validation) — that requires a running service, not just unit tests.

## 8. How the implementation differs from §3 above

Building §3.1 (reuse `inferenceApiKey`) surfaced two problems that changed
the design:

1. **`ServiceCreateRequest`/`ServiceUpdateRequest`'s `_reconcile_ulca_fields`
   silently duplicates whatever's set on `inferenceEndPoint.inferenceApiKey`
   into the deprecated flat `api_key` column, and vice versa** (both are
   written from the same request in one pass). That flat column is *always*
   left unmasked in `service_to_dict()` (a pre-existing, deliberate
   carve-out for the Triton flow). Reusing `inferenceApiKey` for the new
   token would mean it silently lands, in plaintext, in a second column that
   every admin API response exposes unmasked — a direct violation of AC #5.
2. **The `inferenceEndPoint.inferenceApiKey` JSONB field is not actually
   consumed at inference time by anything today** (only the flat `api_key`
   reaches Triton) — so "reuse" would have meant building new,
   security-sensitive behavior on top of a field whose masking/reconciliation
   semantics were never designed for a real secret.

Given that, the token got a **dedicated column** instead:
`mm_services.llm_auth_token` (new migration
`d2e4f6a8b0c2_add_llm_auth_token_to_mm_services.py`), exposed as
`inferenceEndPoint.authenticationToken` — no shared reconciliation with
`api_key`/`inferenceApiKey`, no other code path can ever touch it.

This also changed where masking happens. Since `service_to_dict()` must
still return the flat `api_key` raw (Triton's existing consumption depends
on it) and now also needs to return the new token raw (the internal
resolution route needs it), **masking moved out of the serializer and into
a new `mask_service_secrets()`**, applied by every caller-facing route
(`list_services`, `view_service`, `list_try_it_services`) unconditionally —
admin included. There is no longer a caller of those three routes that ever
receives a real credential value; only the new internal route does.

One planned piece turned out to be dead code and was removed:
`ServiceUpdateRequest._require_billing_fields_on_substantive_edit` already
requires `taskType` on any request that touches `inferenceEndPoint` at all,
so `authenticationToken` can never be set on an update without `taskType`
also being present in the same request — the DB-aware fallback check
sketched in §3.1 (mirroring the schema/taskType cross-check) has no
reachable input to guard against and was deleted rather than shipped as
unreachable code.
