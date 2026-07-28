# Model Consumption Tab — Planning & Analysis

**Status:** Draft for review
**Scope:** Add a "Model Consumption" tab to the Metering screen, showing usage broken down by the actual LLM model (e.g. `agrinet-model`, `google/gemma-4-E4B-it`), not just by service — including a **tenant-wise** breakdown (which tenants are using which models), not just a platform-wide total.

---

## 1. Why this doc exists

Today the Metering screen has a **Service Consumption** tab. It shows, per *service* (NMT, ASR, TTS, LLM, OCR, etc.), how many requests were made, how much was consumed (characters/tokens/minutes), and success/failure rates.

The ask is to add a **Model Consumption** tab that does something similar, but one level deeper — for LLM traffic specifically, broken down by the *actual model* that served the request, since one LLM "service" (like `agrinet-model`) can be backed by different real models over time or across deployments (e.g. `gemma`, `agrinet`). It also needs a **tenant-wise view** — not just "how much did each model get used platform-wide," but "which tenants are using which models," the same way the existing Tenant Consumption tab shows tenants × services today.

Before proposing a design, it's important to explain **what data we already collect** and **what we don't**, because that determines what the new tab can realistically show on day one vs. what needs a small tracking change first.

---

## 2. How Service Consumption works today (for context)

Nothing in this feature reads a database table of "who called what." All the numbers come from **Prometheus** (a metrics system), not from Postgres. The flow is:

1. Every API request updates a few Prometheus counters/histograms (defined in [`libs/ai4i_core/ai4i_core/observability/metrics.py`](libs/ai4i_core/ai4i_core/observability/metrics.py) and populated in [`libs/ai4i_core/ai4i_core/observability/middleware.py`](libs/ai4i_core/ai4i_core/observability/middleware.py)).
2. The backend route [`GET /api/v1/metering/service-consumption`](services/platform-core-service/app/routes/metering.py) calls [`MeteringService.service_breakdown()`](services/platform-core-service/app/services/metering_service.py) which fires a handful of Prometheus queries and shapes the result.
3. The frontend tab [`ServiceConsumptionTab.tsx`](frontend/simple-ui/src/components/metering/ServiceConsumptionTab.tsx) renders a donut chart + a table (Service / Requests / Native consumption / Success % / Failure %).

So: **"mm_services" and "mm_models" (the Postgres tables you registers models/services in) are never consulted for this screen today.** The tenant/service/model names shown come entirely from Prometheus labels attached at request time.

---

## 3. The one fact that shapes this whole design

This is the most important finding from the codebase, so it's called out on its own — and it was corrected after a second look, so this section reflects the corrected understanding.

For LLM requests specifically, the `service_id` label — the same label used everywhere else in the metering feature — **is set to the model the tenant chose, not a generic "llm" bucket.**

Traced through the code:
- The client calls the LLM endpoint OpenAI-style, putting the model choice in a field called `model` (e.g. `"model": "agrinet-model"`).
- The route handler takes that value and puts it straight into `request.state.service_id` — see [`services/inference-service/routes/inference.py:443`](services/inference-service/routes/inference.py#L443): `service_id = payload.get("model", ""); request.state.service_id = service_id`.
- The observability middleware ([`libs/ai4i_core/ai4i_core/observability/middleware.py`](libs/ai4i_core/ai4i_core/observability/middleware.py)) reads that same `request.state.service_id` and stamps it onto **every** metric for that request — including the general request counter, `telemetry_obsv_requests_total{service_id="agrinet-model", ...}`.

So, unlike the other services (NMT/ASR/TTS/...) where `service_id` is a fairly generic identifier, for LLM traffic `service_id` **is** the model dimension we want. That changes the picture from the earlier draft of this doc:

| Metric | What it counts | Carries the model dimension? |
|---|---|---|
| `telemetry_obsv_requests_total` (drives Requests / Success% / Failure% today, for *every* service) | Every request, pass or fail | **Yes, for LLM** — `service_id` *is* the model the client picked |
| `telemetry_obsv_llm_tokens_processed` (drives "tokens processed" for the LLM row) | Token counts, only for requests with a usable token count | Yes — has both `service_id` **and** a separate `model` label (see below) |

**Practical result: we can build the full table (Requests, Tokens, Success %, Failure %) per model, today, with no tracking changes.** This is a much simpler starting point than the original draft assumed.

There is still one finer distinction worth knowing about, covered in §4: the tokens metric also carries a *second*, more granular `model` label — the actual upstream model file (e.g. `google/gemma-4-E4B-it`) resolved from `adapter_config.model_name`. That's a deeper drill-down level, not required for the main table, and is discussed as an optional enhancement in §5.

One caveat that carries over: `telemetry_obsv_requests_total`'s `_count`-style completeness isn't in question here (it counts every request, streaming or not) — the earlier concern about undercounting only applied to the tokens histogram's auto-generated count, which is no longer the primary source for request totals.

---

## 4. Clearing up "same service ID, different models"

Worth double-checking against the actual tables, since there are really **two levels** at which "model" can be defined here, and they answer slightly different questions.

- `mm_services.service_id` is unique — one row per service (e.g. `agrinet-model`, `gemma-model`). This is the identifier tenants actually pick when calling the API (it's what they put in the `model` field of their request), and it's what shows up as `service_id` on every Prometheus metric for that call (§3).
- Each `mm_services` row also points at exactly **one** `mm_models.model_id`, and carries an `adapter_config.model_name` — the *real* upstream model file/checkpoint that request actually gets forwarded to (e.g. `google/gemma-4-E4B-it`). This is captured separately, as the `model` label on the tokens histogram only (`services/inference-service/services/llm_service.py:124-130`).
- What *can* happen over time: an admin can repoint an existing service's `adapter_config.model_name` to a different backing checkpoint (e.g. upgrade `gemma-model`'s backing file) **without changing its `service_id`**. If that happens mid-window, requests under the same `service_id` would show two different values under the finer-grained `model` label.

So there are two valid ways to answer "usage per model," and they serve different audiences:

| Grouping | Answers | Source | Available today? |
|---|---|---|---|
| **By `service_id`** (e.g. `agrinet-model`, `gemma-model`) | "How much traffic went to each model tenants can choose from" — matches how `mm_services` is registered and how tenants think about model selection | `telemetry_obsv_requests_total` + `telemetry_obsv_llm_tokens_processed`, both already carry `service_id` | ✅ Yes — full Requests/Tokens/Success%/Failure% |
| **By real `model`** (e.g. `google/gemma-4-E4B-it`) | "Which underlying model file actually served the traffic" — useful to catch a backing-model swap under one service_id | `telemetry_obsv_llm_tokens_processed` today (tokens only); `telemetry_obsv_requests_total` **can** be extended to carry this too, at very low cost — see §8 | ✅ Tokens available now. Requests/Success%/Failure% at this finer level need the small addition in §8, not currently in place |

**Recommendation: use the `service_id` grouping as the primary "Model Consumption" view** — it's what maps onto `mm_services` registrations (the things ops/admins actually register as "models" in this platform), it's a full match for Service Consumption's table shape, and it needs no tracking changes. The finer `model`-label view can be offered later as an optional drill-down for cases where a service's backing model changed mid-window.

---

## 5. Recommended approach — phased

### Phase 1 (ship first — no tracking changes needed, full table)
A "Model Consumption" tab scoped to LLM only, grouped **by `service_id`** (per §4), showing the same columns as Service Consumption: Requests, Tokens processed, Success %, Failure %. This is a full-parity table, buildable entirely from existing Prometheus metrics — no changes to the shared metrics library required.

### Phase 2 (optional — finer drill-down, cheaper than it first looked)
For cases where the same `service_id` was repointed to a different real backing model mid-window (§4), offer an optional secondary breakdown by the real `model` label (from `adapter_config.model_name`). Tokens are already available for this today; §8 below adds a small, low-risk change to the shared metrics library so Requests/Success%/Failure% become available at this level too, not just tokens — turns out to be only a two-line change (one new label, one new call argument, single call site), not the bigger "touches every service" change originally assumed. Still optional for launch — add if this drill-down turns out to matter in practice, or now if it's cheap enough to just include.

### Phase 3 (optional polish)
Look up nicer display names from `mm_services`/`mm_models` (e.g. the service's human-readable `name` field instead of the raw `service_id` string) if the registered service_ids aren't already tenant-friendly. Not required — the raw service_id strings (`agrinet-model`, `gemma-model`) are already fairly readable — so treat as a nice-to-have.

**Recommendation: build Phase 1 now.** It already delivers the full ask — request volume, token consumption, and success/failure rate, per model — with no changes to shared tracking code.

---

## 6. What the new tab should show (Phase 1)

Mirrors the Service Consumption tab's layout so it feels familiar:

- **Two KPI cards** at the top:
  - "Most used model" (by tokens processed)
  - "Number of active models" in the selected time window
- **A donut chart** — share of total tokens processed, per model.
- **A breakdown table:**

  | Model | Total requests | Tokens processed | Success rate % | Failure rate % |
  |---|---|---|---|---|
  | agrinet-model | 42,100 | 1,204,300 | 98.20% | 1.80% |
  | gemma-model | 31,850 | 980,120 | 97.65% | 2.35% |
  | ... | ... | ... | ... | ... |

- Same controls as the rest of the Metering screen: time window (1h/24h/7d/30d), tenant filter (admin only), refresh button — these are shared already, no new UI needed for them.

This is already a full match for the Service Consumption table shape — no "coming soon" columns, no caveats needed for Phase 1.

### Tenant-wise breakdown

There are two different ways "tenant-wise" shows up, and both should be covered:

1. **Single-tenant view.** When a Platform Admin picks one tenant from the tenant filter (or a Tenant Admin is simply viewing their own account), the table above already scopes itself to that one tenant — this falls out of Phase 1 for free, the same way the tenant filter already works on Service Consumption today.
2. **Cross-tenant matrix — "which tenants are using which models."** This is the part that needs a new piece, modeled directly on the existing Tenant Consumption tab, which already shows exactly this shape for services: a **"Usage by tenant & model" heatmap** — top-N tenants as rows, models as columns, each cell showing that tenant's request count and % of their own total for that model, plus a row total. See [`TenantServiceHeatmapSection.tsx`](frontend/simple-ui/src/components/metering/TenantServiceHeatmapSection.tsx) for the existing version of this (services instead of models).

   This second view is **Platform-Admin-only**, same restriction as today's tenant × service heatmap (a Tenant Admin only ever sees their own row, so a cross-tenant matrix isn't meaningful for them — covered by view 1 instead).

   One structural difference from the existing services heatmap worth flagging: the list of services is small and fixed (~11 keys, hardcoded in `SERVICE_BREAKDOWN_CONFIG`/`METERING.HEATMAP.SERVICES`), but the list of models is **not fixed** — it's whatever's registered in `mm_services` and actually saw traffic in the window. So the model heatmap's columns need to come from the query results themselves (e.g. top-K models by volume in that window), not from a static list — see §7 and §9 for what that means for the code.

---

## 7. Backend changes (Phase 1)

All new code, following the existing metering feature's own layout (routes → service → promql-builder helpers, no repository/DB layer needed since this is Prometheus-only, same as Service Consumption).

| File | Change |
|---|---|
| [`app/utils/metering_promql_builder.py`](services/platform-core-service/app/utils/metering_promql_builder.py) | Add an LLM-only endpoint selector (reuse `ENDPOINT_TO_TASK`/the `/api/v1/chat(/completions)?` pattern already defined for the `llm` task) so model-breakdown queries only look at LLM traffic |
| [`app/services/metering_service.py`](services/platform-core-service/app/services/metering_service.py) | Add a new method `MeteringService.model_breakdown(tenant, time_range)` — same shape and same two-query pattern as the existing `service_breakdown()` method (total + success, via `telemetry_obsv_requests_total`), but grouped **by `service_id`** instead of by endpoint/task, filtered to LLM endpoints only. Add one more query grouped by `service_id` against `telemetry_obsv_llm_tokens_processed_sum{token_type="total"}` for the tokens column |
| [`app/schemas/metering.py`](services/platform-core-service/app/schemas/metering.py) | Add `ModelRow` (model, requests, native_units, native_unit_suffix, success_pct, failure_rate_pct) and `ModelConsumptionResponse` (scope, summary, model_breakdown, degraded, generated_at) — effectively identical in shape to `ServiceRow` / `ServiceConsumptionResponse`, since the underlying computation is the same pattern, just grouped by `service_id` instead of by task |
| [`app/routes/metering.py`](services/platform-core-service/app/routes/metering.py) | Add `GET /api/v1/metering/model-consumption`, copying the existing `/service-consumption` route's auth/scope/redis-cache pattern (cache key `metering:model-consumption:v1:{window}:{tenant}:{role}`) |

No changes needed to `app/dependencies/services.py` — the existing `get_metering_service()` dependency already provides everything this needs. No changes needed to the shared metrics library either — `service_id` is already recorded on every LLM request.

### Tenant × model matrix (for the "Usage by tenant & model" heatmap)

This mirrors [`MeteringService.usage_by_tenant_service()`](services/platform-core-service/app/services/metering_service.py#L456), which already does the tenant × service version.

| File | Change |
|---|---|
| [`app/services/metering_service.py`](services/platform-core-service/app/services/metering_service.py) | Add `MeteringService.usage_by_tenant_model(limit, time_range, tenant=None)` — same query shape as `usage_by_tenant_service()` (`sum by(tenant, service_id) (...)`), but against the LLM-only endpoint selector from §7 above instead of all inference endpoints, and grouped by `service_id` instead of by `exported_endpoint`/task. Unlike `usage_by_tenant_service()`, the set of "columns" (models) can't come from a static config dict — build it from the query results themselves (e.g. the top-K distinct `service_id` values by total volume across the returned tenants) |
| [`app/schemas/metering.py`](services/platform-core-service/app/schemas/metering.py) | The existing `TenantServiceRow`/`ServiceEntry` shapes are already generic (`services: dict[str, ServiceEntry]` is just a string-keyed map) — reusable as-is for models, or duplicate as `TenantModelRow`/`ModelEntry` for clarity. Add a `models: list[{key, display_name}]` list alongside the rows, same as `usage_by_tenant_service()` returns a `services` list today, so the frontend knows what columns exist |
| [`app/routes/metering.py`](services/platform-core-service/app/routes/metering.py) | In the new `/model-consumption` route, gather `svc.model_breakdown(...)` and `svc.usage_by_tenant_model(...)` together (same `asyncio.gather` pattern as `/tenant-consumption` gathers `tenant_ranking` + `usage_by_tenant_service`), and only run/return the heatmap when the caller is a Platform Admin |
| `app/schemas/metering.py` | Add `usage_by_tenant_model: list[TenantModelRow]` (or reused `TenantServiceRow`) to `ModelConsumptionResponse` |

### Example query shape (Phase 1)

```promql
# Requests per model (LLM endpoints only), grouped by service_id
sum by (service_id) (
  telemetry_obsv_requests_total{
    exported_endpoint=~"/api/v1/(chat|chat/completions)",
    tenant!="unknown"
  }
)

# Tokens processed per model, same grouping
sum by (service_id) (
  telemetry_obsv_llm_tokens_processed_sum{token_type="total", tenant="tenant-123"}
)
```
Both wrapped in the same `increase()`-based time-window logic already used elsewhere in `metering_service.py`, so the numbers are consistent with how other tabs compute "usage in the last N hours." This mirrors `service_breakdown()` almost line-for-line — the only real difference is the `by (service_id)` grouping and the endpoint filter being LLM-only instead of per-task.

---

## 8. Backend changes (Phase 2 — optional, real-backing-model drill-down)

**Update: this was re-examined at the user's request ("can I add a `model` label to `telemetry_obsv_requests_total`, just for LLM?") and turns out to be a genuinely small, low-risk change** — smaller than the original draft of this section assumed. Recording it here as a requirement that can be picked up whenever, not just a hypothetical.

### Is it possible to add a `model` label "just for LLM"?

Almost — with one caveat worth understanding. Prometheus counters/histograms require every observation to supply a value for *every* declared label, so the label itself can't be "LLM-only" at the metric-definition level. In practice this is a non-issue here, because:

- `telemetry_obsv_requests_total` has exactly **one call site** in the whole codebase: [`libs/ai4i_core/ai4i_core/observability/middleware.py:224`](libs/ai4i_core/ai4i_core/observability/middleware.py#L224), inside `_record_metrics()`.
- That same function already computes an `llm_model` variable ([`middleware.py:93`](libs/ai4i_core/ai4i_core/observability/middleware.py#L93)) which defaults to `""` and is only ever populated for `service_type == "llm"` — it's already being passed to `track_llm_tokens()` a few lines later ([`middleware.py:240`](libs/ai4i_core/ai4i_core/observability/middleware.py#L240)).

So non-LLM requests (NMT, ASR, TTS, OCR, ...) would simply get `model=""` on every request — same as today's behavior, no new plumbing needed at those call sites, and no risk of breaking their existing metrics or dashboards (an unused, constant-empty label doesn't change how `sum()`/`sum by(...)` queries behave for label sets that don't reference it).

### The actual change

| File | Change |
|---|---|
| [`libs/ai4i_core/ai4i_core/observability/metrics.py`](libs/ai4i_core/ai4i_core/observability/metrics.py#L28-L33) | Add `"model"` to the label list of `enterprise_requests_total` (the `telemetry_obsv_requests_total` Counter), and add a `model: str = ""` parameter to `track_request()` ([`metrics.py:153`](libs/ai4i_core/ai4i_core/observability/metrics.py#L153)), passed through to `.labels(...)` |
| [`libs/ai4i_core/ai4i_core/observability/middleware.py:224`](libs/ai4i_core/ai4i_core/observability/middleware.py#L224) | Pass `model=llm_model or ""` into the existing `track_request(...)` call — `llm_model` is already computed and already `""` for every non-LLM request, so this is a one-line addition, not a new extraction path |
| [`app/services/metering_service.py`](services/platform-core-service/app/services/metering_service.py) / `model_breakdown()` | Add a query grouped by `model` (not `service_id`) against `telemetry_obsv_requests_total` (LLM endpoints only) for the finer-grained Requests/Success%/Failure%, alongside the existing tokens-by-`model` query |
| `schemas/metering.py` | Add an optional nested `real_model_breakdown: list[ModelRow]` on the response, or a separate lightweight endpoint, for surfacing this as a drill-down under each `service_id` row |

Because this touches a shared library used by every service, it still needs a proper rollout — bump the `ai4i_core` package version, redeploy every dependent service, and confirm (e.g. in a staging environment) that NMT/ASR/TTS/OCR/etc. keep emitting metrics correctly with the new label defaulting to empty. But the code change itself is small and doesn't require touching each service's own code.

**Worth calling out as a follow-up to Phase 1, not a blocker for it** — since Phase 1 already ships the full table at the `service_id` level with zero library changes.

---

## 9. Frontend changes (Phase 1)

Following the exact same file layout as Service Consumption:

| File | Change |
|---|---|
| [`config/meteringConstants.ts`](frontend/simple-ui/src/config/meteringConstants.ts) | Add `SUB_TAB.MODEL = "model"`, add an entry to `SUB_TABS` / `TENANT_SUB_TABS`, add a `SECTIONS.MODEL` block (titles/labels), add a color map for models |
| `types/metering.ts` | Add `ModelConsumptionResponse` / `ModelRow` TypeScript types, mirroring `ServiceConsumptionResponse` |
| `services/dto/schemas/metering.ts` | Add a zod schema for the new response, mirroring `serviceConsumptionResponseSchema` |
| `services/apiEndpoints.ts` | Add `metering.modelConsumption` endpoint constant |
| [`services/meteringService.ts`](frontend/simple-ui/src/services/meteringService.ts) | Add `fetchMeteringModelConsumption()`, copying `fetchMeteringServiceConsumption()` |
| [`hooks/useMeteringDashboard.ts`](frontend/simple-ui/src/hooks/useMeteringDashboard.ts) | Add a `modelQuery` react-query hook, enabled when `subTab === METERING.SUB_TAB.MODEL`, same pattern as `serviceQuery` |
| **New file** `components/metering/ModelConsumptionTab.tsx` | Clone of [`ServiceConsumptionTab.tsx`](frontend/simple-ui/src/components/metering/ServiceConsumptionTab.tsx) — same KPI cards + donut + table layout, same columns (Model / Requests / Tokens / Success % / Failure %). For the adopter/admin view, also renders the tenant × model heatmap below the table (see next row) |
| [`components/metering/UsageDashboardPanels.tsx`](frontend/simple-ui/src/components/metering/UsageDashboardPanels.tsx) | Render `<ModelConsumptionTab>` when `subTab === METERING.SUB_TAB.MODEL`, in both the tenant and adopter panel components |

No new shared UI components are needed for the main table — `MeteringDonutChart`, `MeteringDataTable`, `MeteringSectionCard`, `MeteringAsyncState` are all already generic and reusable as-is.

### Tenant × model heatmap (Platform Admin view only)

[`TenantServiceHeatmapSection.tsx`](frontend/simple-ui/src/components/metering/TenantServiceHeatmapSection.tsx) can't be reused unmodified — it reads its column list from a hardcoded catalog, `METERING.HEATMAP.SERVICES` (`config/meteringConstants.ts`), which works for services because there are only ~11 of them and they never change. Models don't have that kind of fixed list.

| File | Change |
|---|---|
| **New file** `components/metering/TenantModelHeatmapSection.tsx` | Same layout/behavior as `TenantServiceHeatmapSection.tsx` (sticky tenant column, colored cells by intensity, row totals, legend), but takes its column list from the API response's `models` list (§7) instead of a hardcoded catalog — no "select services" filter menu needed unless the model list gets long enough to warrant one |
| `types/metering.ts` | Add `TenantModelRow` type (or reuse `TenantServiceRow` if the shapes end up identical) and a `ModelColumn { key, display_name }` type for the dynamic column list |
| [`hooks/useMeteringDashboard.ts`](frontend/simple-ui/src/hooks/useMeteringDashboard.ts) | The existing `topN` state (already used by Tenant Consumption's heatmap) can be reused here rather than adding a second one, if both heatmaps should share the same "Top 10 / Top 25" control |
| `components/metering/ModelConsumptionTab.tsx` | Render `<TenantModelHeatmapSection>` only when `roleViewConfig` indicates a Platform Admin, mirroring how `AdopterDashboardPanels` (not `TenantDashboardPanels`) is the one that renders `TenantConsumptionTab`/its heatmap today |

---

## 10. Open questions to decide before/while building

1. **Where should this tab live?** As a new top-level sub-tab next to "Service Consumption" (like this doc assumes), or nested inside Service Consumption only when the LLM row is expanded/clicked? A top-level tab is simpler and matches the ask more directly.
2. **Should Tenant Admins see this too, or only Platform Admins?** Service Consumption is visible to both — recommend the same for consistency. The cross-tenant heatmap (§6/§7/§9) would stay Platform-Admin-only either way, matching Tenant Consumption's existing restriction.
3. **Is the `service_id` grouping (§4) the right definition of "model" for this feature?** It matches how models are registered in `mm_services` and how tenants select them via the API, and it's what makes the full table possible without tracking changes. Worth confirming this matches what stakeholders picture when they say "agrinet, gemma, etc." — if they specifically mean the real backing model file rather than the registered service, that's the Phase 2 drill-down (tokens only) instead.
4. **Friendly model names (Phase 3)** — worth doing now, or fine to launch with raw `service_id` strings (e.g. `agrinet-model`) as-is?
5. **How many model columns should the heatmap show at once?** Since models aren't a small fixed catalog like services, an admin with dozens of registered LLM services could end up with a very wide table. Worth deciding a default (e.g. top 10 models by volume, matching the existing `topN` tenant control) rather than showing every model that ever saw traffic.
6. **Should the Phase 2 metrics-library change (§8) be bundled into the initial launch, or done as a fast-follow?** It's now confirmed to be a small, low-risk change (one new label, one new call argument, single call site) — cheap enough that it could realistically go in alongside Phase 1 rather than waiting. The main reason to still call it "Phase 2" is the rollout mechanics (bumping a shared package version and redeploying every dependent service), which is a bigger lift than the code change itself.

---

## 11. Rough effort shape

- **Phase 1 (full model breakdown tab — Requests, Tokens, Success %, Failure %, platform-wide and single-tenant-scoped):** small — one new backend method + route + schema, one new frontend tab component + wiring, all reusing existing shared pieces and requiring no changes to the shared metrics library. Comparable in size to how Service Consumption itself was built.
- **Tenant × model heatmap (cross-tenant matrix, Platform-Admin-only):** small-to-medium — one new backend method (close copy of `usage_by_tenant_service()`), and one new frontend component, since the existing heatmap component's fixed-column assumption doesn't carry over to a dynamic model list.
- **Phase 2 (optional real-backing-model drill-down, incl. the `model`-on-`telemetry_obsv_requests_total` addition):** the metering query work is a small, independent add-on (one extra query grouped by a label that already exists for tokens, or that becomes available via the §8 change for requests). The §8 metrics-library change itself is a two-line code change, but carries shared-library rollout overhead (version bump + redeploy across every service + a staging sanity check) — small in code size, moderate in process/coordination.
- **Phase 3 (friendly names):** small, independent, can be done anytime after Phase 1.
