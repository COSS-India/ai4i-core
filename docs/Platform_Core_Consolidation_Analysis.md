# Consolidation Analysis: Moving Services into platform-core-service

**Question:** Can `pii-guard-service`, `smr-service`, `policy-service`, and `request-profiler-service` be moved into `platform-core-service`? If so, how?

**Scope:** High-level architecture and feasibility only. Not a code-level refactor.

---

## TL;DR

| Service | Move into platform-core? | Confidence | Effort estimate |
|---|---|---|---|
| **smr-service** | **Yes** | High | Small — 1–2 days |
| **policy-service** | **Yes** (it's a skeleton — fold its planned scope in) | High | Small — scope decision, not migration |
| **pii-guard-service** | **No** | High | N/A — keep separate |
| **request-profiler-service** | **No** (consider folding into `inference-service` instead) | Medium | N/A — better belongs elsewhere |

Two of four are good consolidation candidates. The other two have characteristics that make them poor fits for platform-core specifically.

---

## What platform-core-service is today

Looking at [`services/platform-core-service/app/`](../services/platform-core-service/app/):

- **Stack:** FastAPI + SQLAlchemy 2.x async + asyncpg, standard layered architecture (core / dependencies / middleware / models / repositories / routes / schemas / services / utils).
- **Database:** `core_db` (Postgres). Owns the `models` and `services` tables — the canonical model registry.
- **Public surface:** `/api/v1/model-management/services/*` and `/api/v1/model-management/models/*` (per the nginx gateway: `set $upstream_model_mgmt http://platform-core-service:8095;`).
- **Role:** authoritative source for "what models/services exist, who can use them, what their endpoints are."
- **Maturity:** mature — has `tests/`, uses `ai4icore-core` for bootstrap/exceptions/etc.

So "moving X into platform-core" means making X a set of routes + services + repositories inside this app, sharing its DB connection pool and config.

---

## 1. smr-service → ✅ **Move it in**

### What it does

[`services/smr-service/main.py`](../services/smr-service/main.py) — Smart Model Router. Given a `task_type` and inference payload, picks the right `serviceId` to route to. Process (per current code):

1. Receive `POST /select` with `{task_type, request_body, user_id, tenant_id}` + policy headers.
2. **If `X-Latency-Policy` / `X-Cost-Policy` / `X-Accuracy-Policy` headers are NOT supplied**, call `policy-engine` over HTTP to fetch the tenant's default policy (`POST {POLICY_ENGINE_URL}/v1/policy/evaluate`). See "Broken downstream" below.
3. **If `X-Request-Profiler: true` header is supplied**, call `request-profiler-service` (`POST {REQUEST_PROFILER_SERVICE_URL}/api/v1/profile`) to score the input's complexity/domain/language. Used as a tie-breaker.
4. Query the local DB for published services matching `task_type` (via `db_operations.list_all_services` — uses copied SQLAlchemy models).
5. Score candidates against the policy + (optionally) profiler results. Pick primary + fallback.
6. Return `{serviceId, fallbackServiceId, tenant_policy, service_policy, scoring_details, request_profiler}`.

### ⚠️ Broken downstream: policy-engine

[`services/policy-engine/`](../services/policy-engine/) is **empty of source code** — only `__pycache__/` artifacts remain (bytecode from ~8 deleted files: `main.py`, `app/billing_routes.py`, `app/billing_schemas.py`, `app/database.py`, `app/db_models.py`, `app/models.py`, `app/repository.py`, `app/__init__.py`). The implementation was deleted; the directory and the SMR env var (`POLICY_ENGINE_URL=http://policy-engine:8095`) are vestigial. There is **no `policy-engine` service in [docker-compose-local.yml](../docker-compose-local.yml)** either.

Operational consequence: in [`smr-service/main.py:124-132`](../services/smr-service/main.py#L124-L132) the policy-engine call is wrapped to raise `HTTPException(503, "POLICY_ENGINE_UNAVAILABLE")` on connection failure. So **any SMR request without all three policy headers fails today**. SMR only "works" when callers explicitly pass `X-Latency-Policy` / `X-Cost-Policy` / `X-Accuracy-Policy`, which bypasses the broken path.

Implication for consolidation:
- Don't migrate the policy-engine HTTP call as-is. Either (a) drop it and require headers explicitly, or (b) reinstate the policy-engine logic inside platform-core (it appears to have been billing-related per the deleted filenames — different scope from the policy-service scaffold; see §2).
- This is a pre-existing brokenness, not a consolidation risk. Worth flagging to the team regardless of whether you do the move.

### Why this fits platform-core naturally

Two things make this a near-trivial move:

**1. SMR already reads platform-core's DB tables.** The smoking gun is in [`services/smr-service/models.py:1-5`](../services/smr-service/models.py#L1-L5):

```python
"""
Database models and enums for SMR service.
These are copied from model-management-service to enable direct DB access.
"""
```

It maintains a hand-copied duplicate of `Model` and `Service` SQLAlchemy classes. This is a drift hazard — any schema change to platform-core's tables silently breaks SMR until someone notices and re-copies. Moving SMR into platform-core eliminates this duplication: one source of truth for the models, one DB pool.

**2. SMR has no state of its own.** No tables it owns, no in-memory caches refreshed on a timer, no Kafka producers, no Redis pubsub. It's pure HTTP orchestration + a few SQL queries. The full filesystem layout is 4 files: `main.py`, `models.py` (duplicates), `db_connection.py`, `db_operations.py`. Nothing to migrate other than route + query logic.

### How

- Add `app/routes/smr.py` to platform-core exposing `POST /api/v1/model-management/smr/select` (or split out to `/api/v1/smr/select` if you want a separate prefix).
- Add `app/services/smr_service.py` with the routing logic that today lives in `smr-service/main.py`. It can call the existing `ServiceRepository` for DB queries (replacing the copied `db_operations.py`).
- Decide upfront what to do about the policy-engine call (see "Broken downstream" above). Either drop it (require headers from callers) or reimplement that logic in-process if the billing-policy behavior is actually needed.
- Keep the `request-profiler-service` HTTP call as-is — it's a working, opt-in dependency (gated by `X-Request-Profiler` header). Just lift the `call_request_profiler` function into platform-core.
- Update [`services/inference-service/`](../services/inference-service/) callers: change `SMR_SERVICE_URL=http://smr-service:8097` → `MODEL_MANAGEMENT_SERVICE_URL/api/v1/model-management/smr/select` (or whatever path you pick).
- Remove `smr-service:` block from [docker-compose-local.yml:826](../docker-compose-local.yml#L826).
- Delete `services/smr-service/`.

### Bonus

Co-locating SMR with the model registry means SMR's "list candidate services" query is in-process instead of cross-service. Saves one DB round-trip-worth of overhead per inference request, and keeps the read consistent (no risk of a stale replica).

### Risks

- **Larger blast radius for platform-core.** A bug in SMR's routing logic now affects every model-management API consumer. Mitigation: keep routes namespaced, add integration tests covering the routing path (platform-core already has `tests/`).
- **Different SLO profile.** SMR is on the inference hot path (called per request). Model-management is also called per request today (for endpoint resolution) but is generally light. Adding SMR's policy-engine + profiler HTTP calls per request raises platform-core's p95 latency contribution. Worth checking your observability dashboard after the move; could need a connection-pool tune for the downstream HTTP clients.

---

## 2. policy-service → ✅ **Fold its scope in (it's a skeleton)**

### Current state

From [`services/policy-service/README.md`](../services/policy-service/README.md):

> A FastAPI microservice scaffold for policy-related functionality. **This is an initial skeleton; business logic and endpoints will be added later.**

The layout shows routes outlined for `policies.py`, `tenant_policies.py`, `pii_types.py`, `audit_logs.py`, `health.py` — but no implementations yet.

### Why this is the easiest decision

There's nothing to migrate — the question is just *where do these planned features get built when you build them*. Two options:

| Option | Pros | Cons |
|---|---|---|
| **Build inside platform-core** | One service, one DB pool. Policies and tenant_policies are closely tied to the model/service registry (which services a tenant can use, what their tier-policy allows). Reads natural. | Platform-core grows in scope from "model registry" to "model registry + policy engine." |
| **Build the skeleton out** | Cleaner separation if policy logic gets large and independent. | Another service to deploy, network hop, DB-or-not decision, drift risk like SMR. |

### Recommendation

Fold it into platform-core unless you have a concrete reason to keep it independent (e.g. plans for a separate policy team, very different scaling profile, or a policy-as-code engine like OPA where the boundary makes sense). Most of the *planned* routes (`policies.py`, `tenant_policies.py`) directly reference tables that would live in `core_db` anyway.

Caveats:

- `pii_types.py` and `audit_logs.py` in the planned scope likely overlap with what `pii-guard-service` already owns (see §3). Decide whether policy-service was meant to *configure* PII types/audit logs (admin UI for pii-guard) versus *execute* them. The former belongs in platform-core; the latter belongs in pii-guard-service.
- **`policy-service` and `policy-engine` are NOT duplicates.** They are two different services with different domains:
  - `policy-service/` — scaffold focused on PII / tenant policies / audit log admin (per the planned route filenames).
  - `policy-engine/` — empty now, but its deleted bytecode artifacts (`billing_routes.py`, `billing_schemas.py`, `db_models.py`, `repository.py`) indicate it was a billing-oriented engine. SMR still tries to call it for latency/cost/accuracy policy evaluation (see §1 — the call is dead-in-the-water).
  - Whatever you do with policy-service, separately decide: do you need the billing-policy logic policy-engine used to provide? If yes, reinstate it (likely inside platform-core as part of the SMR consolidation). If no, delete `services/policy-engine/` entirely and strip the `POLICY_ENGINE_URL` from SMR.

### How

1. Decide the scope of policy-service (admin-side configuration of policies vs. runtime evaluation).
2. Move that scope into platform-core as `app/routes/policies.py`, `app/services/policy_service.py`, etc.
3. Delete `services/policy-service/` and the compose entry.
4. Decide what to do with `services/policy-engine/` (leftover from a prior design — likely delete too if SMR is also being moved).

---

## 3. pii-guard-service → ❌ **Keep separate**

### What it does

[`services/pii-service/main.py`](../services/pii-service/main.py) — a 730-line service that detects and redacts PII from text. The actual flow per request:

1. Resolve the tenant's PII domain (from `tenant_pii_domain_map`).
2. Load the active policy for that domain (rules list — what entity types to redact, what to replace them with).
3. Run a 3-layer detection:
   - **AI extraction:** HTTP call to `ner-service` to get entity tags.
   - **Regex layer:** pattern matching against tenant-domain rules + a hand-tuned knowledge base of patterns.
   - **Quasi-identifiers:** keyword matching for occupations, gender terms, etc.
4. Apply the redaction action per rule (REDACT_TAG, MASK, etc.).
5. Async-write an audit log entry to `audit_logs` table + best-effort publish to Kafka.

### Why this doesn't belong in platform-core

This is a different kind of service in three independent ways:

**1. Separate database.** From the source: `DB_NAME = os.getenv("DB_NAME", "pii_guardrail")`. Owns five tables: `pattern_library`, `geo_library`, `domain_policies`, `tenant_pii_domain_map`, `audit_logs`. None of these have any relationship to the `models`/`services` schema in `core_db`. Merging would require either a schema migration into `core_db` (with all the associated risk) or running platform-core against two databases (which loses the "single DB pool" benefit of consolidating).

**2. Different runtime characteristics.** The service maintains a `KnowledgeBase` in memory loaded from DB at startup, subscribes to a Redis pubsub channel for invalidation events, and runs a Kafka producer. Platform-core is a stateless request/response service. Moving pii-service in means adding all that startup choreography, Redis pubsub task management, and a Kafka producer lifecycle to platform-core's lifespan — none of which it needs today.

**3. Different domain.** Model management is "what models exist and how are they reached." PII guardrail is "what entities should I detect in this text and how do I redact them." There's no shared vocabulary, no shared dependency direction, no natural reason for one to know about the other. The only weak link is "both have admin UI endpoints for tenant configuration" — but that's a thin justification for fusing two unrelated bounded contexts.

### What about consolidating it elsewhere?

If your concern is "too many services," there's a stronger argument for a future *guardrails* service that bundles pii-guard with any other content-safety capabilities you build (toxicity filter, prompt-injection detector, etc.). That's a different consolidation though — not "into platform-core."

### Recommendation

Leave pii-guard as is. The only platform-core-adjacent piece is the `tenant_pii_domain_map` table — and even that's better off staying in `pii_guardrail` DB where it's read on every redact request.

---

## 4. request-profiler-service → ❌ **Don't put it in platform-core**

### What it does

[`services/request-profiler/README.md`](../services/request-profiler/README.md) — Production-ready microservice that takes text and returns a profile:

- **Domain classification** (medical, legal, technical, finance, casual, general) via scikit-learn pipeline
- **Complexity scoring** (LOW/HIGH) via a regressor (vocabulary sophistication 40%, syntactic 30%, semantic 20%, length 10%)
- **Language detection** via fastText (`lid.176.ftz`)
- **Entity / terminology density** features

Loads `.pkl` model files (`domain_pipeline.pkl`, `complexity_regressor.pkl`) and a fastText binary into memory at startup. Then it's pure CPU-bound inference per request.

### Why this is a bad fit for platform-core specifically

**1. Heavy ML dependencies.** scikit-learn + fastText alone add ~400MB to the image. Platform-core today depends on standard service infra (FastAPI, asyncpg, redis, slowapi). Adding ML stack inflates the image, slows builds, complicates security patching cycles.

**2. Different scaling profile.** Profiler is CPU-bound per request. Platform-core is IO-bound (DB queries, JSON responses). They want different autoscaling triggers and probably different instance shapes. Bundling them together means you scale both based on whichever signal is louder.

**3. Memory footprint and startup cost.** Pre-trained models held in memory; cold-start time goes up.

**4. Profiler is, structurally, an inference service.** It takes text in, returns a structured prediction. That's *exactly* what `inference-service` is now built for. The new unified inference design with `task_type` could absorb profiler as `task_type=PROFILE` (or `task_type=REQUEST_PROFILE`). Then it lives in the right architectural layer.

### Recommendation

**Don't move into platform-core.** Two reasonable paths:

- **Status quo.** Keep request-profiler-service as a standalone microservice that SMR calls over HTTP. Works today, low risk.
- **Fold into inference-service** as another task type. Same image, same scaling story, same `/api/v1/inference` entry point as every other model. Requires the inference-service factory/orchestrator to learn about ML-based profiling — moderate change, but it's the architecturally consistent path. Removes the need for SMR to know about a separate profiler URL.

---

## Putting it together: target architecture

If you act on the two "Yes" recommendations, the topology becomes:

```
                            ┌────────────────────────────┐
                            │   inference-service        │
                            │   POST /api/v1/inference   │
                            └────────────┬───────────────┘
                                         │ resolve serviceId
                                         ▼
            ┌────────────────────────────────────────────────────────┐
            │  platform-core-service                                  │
            │    /api/v1/model-management/services/*                  │
            │    /api/v1/model-management/models/*                    │
            │    /api/v1/model-management/smr/select   ← SMR moved in │
            │    /api/v1/policies/*                    ← scaffold     │
            │                                            absorbed     │
            └────────────────┬─────────────────┬─────────────────────┘
                             │                 │
                  ┌──────────▼──────┐    ┌────▼─────────────────────┐
                  │ request-        │    │ pii-guard-service        │
                  │ profiler-svc    │    │ (stays separate)         │
                  │ (still HTTP)    │    └──────────────────────────┘
                  └─────────────────┘
```

**Services removed:** `smr-service`, `policy-service` (scaffold), `policy-engine` (legacy, not in compose).

**Services kept:** `pii-guard-service`, `request-profiler-service`.

**Net effect on compose:** 14 non-inference services → 12.

---

## Risks and open questions

1. **policy-engine is gutted, SMR still calls it.** Confirmed: `services/policy-engine/` has no `.py` files, only stale `__pycache__/` artifacts. SMR's `call_policy_engine_for_smr` returns 503 on every call (DNS failure). The only reason SMR isn't completely broken is that callers can supply `X-Latency-Policy` / `X-Cost-Policy` / `X-Accuracy-Policy` headers explicitly, which bypasses the policy-engine HTTP call entirely. **Action required regardless of consolidation:** decide whether to reinstate this logic (in-process, inside platform-core) or remove the calling code path and require explicit policy headers.

2. **SMR's downstream calls after consolidation.** Moving SMR into platform-core means platform-core's request handlers now make outbound HTTP calls to `request-profiler-service` (when `X-Request-Profiler: true`). That's one new external dependency for platform-core. If you also handle the policy-engine question by reinstating that logic in-process, the *only* external HTTP dependency added is request-profiler.

3. **Inference-service is currently outside Docker.** The integration with platform-core (for SMR) works today over the host bridge (`host.docker.internal`). When inference-service moves into Docker, this becomes a normal in-network call. Either way, the move-SMR-in plan doesn't depend on this.

4. **Test coverage.** Platform-core has `tests/`; smr-service appears to have none. Before merging, audit SMR's behavior — what does the routing logic actually do? — and add at least scoring/fallback tests before/after the move. The broken-policy-engine path is a perfect test target: regression-protect whichever decision you make.

5. **Tenant scoping of routes.** Pay attention to which routes belong on the `/api/v1/auth/validate`-gated path vs. internal-only. SMR is currently called by inference-service (a trusted service); if it gets absorbed into platform-core's public namespace, you may want to gate it behind a different auth profile than the model registry CRUD APIs.

6. **Two empty-shell directories worth cleaning up regardless.** `services/policy-engine/` (deleted source, only `.pyc` left) and `services/policy-service/` (scaffold-only) are both pollution if not used. Even without consolidation, removing `policy-engine/` after deciding what to do with SMR's call would reduce confusion. The `.pyc` files in `__pycache__` are the only thing that gives the impression a service exists there.

---

## Decision summary

| Move | When | Risk |
|---|---|---|
| **smr-service → platform-core** | Anytime; small, contained change | Low — bug-class limited to routing logic |
| **policy-service scope → platform-core** | When you're ready to build policy features | Low — there's nothing to break |
| **pii-guard-service → keep separate** | — | — |
| **request-profiler-service → keep separate** OR fold into inference-service | If folding, do it as part of a larger inference-service task-type expansion | Medium — touches the inference orchestrator |

Both Yes moves can be done independently. Doing SMR first is the higher-leverage win (kills the duplicate SQLAlchemy models immediately).
