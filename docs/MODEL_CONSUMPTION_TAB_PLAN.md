# Model Consumption Tab — Planning & Analysis

**Status:** Draft for review
**Scope:** Add a "Model Consumption" tab to the Metering screen, showing usage broken down by the actual LLM model (e.g. `agrinet-model`, `google/gemma-4-E4B-it`), not just by service.

---

## 1. Why this doc exists

Today the Metering screen has a **Service Consumption** tab. It shows, per *service* (NMT, ASR, TTS, LLM, OCR, etc.), how many requests were made, how much was consumed (characters/tokens/minutes), and success/failure rates.

The ask is to add a **Model Consumption** tab that does something similar, but one level deeper — for LLM traffic specifically, broken down by the *actual model* that served the request, since one LLM "service" (like `agrinet-model`) can be backed by different real models over time or across deployments (e.g. `gemma`, `agrinet`).

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
| **By real `model`** (e.g. `google/gemma-4-E4B-it`) | "Which underlying model file actually served the traffic" — useful to catch a backing-model swap under one service_id | `telemetry_obsv_llm_tokens_processed` only | ✅ Tokens only, ❌ no request/success/failure breakdown at this finer level |

**Recommendation: use the `service_id` grouping as the primary "Model Consumption" view** — it's what maps onto `mm_services` registrations (the things ops/admins actually register as "models" in this platform), it's a full match for Service Consumption's table shape, and it needs no tracking changes. The finer `model`-label view can be offered later as an optional drill-down for cases where a service's backing model changed mid-window.

---

## 5. Recommended approach — phased

### Phase 1 (ship first — no tracking changes needed, full table)
A "Model Consumption" tab scoped to LLM only, grouped **by `service_id`** (per §4), showing the same columns as Service Consumption: Requests, Tokens processed, Success %, Failure %. This is a full-parity table, buildable entirely from existing Prometheus metrics — no changes to the shared metrics library required.

### Phase 2 (optional — finer drill-down)
For cases where the same `service_id` was repointed to a different real backing model mid-window (§4), offer an optional secondary breakdown by the real `model` label (from `adapter_config.model_name`) — tokens only, since that's the only metric carrying that finer label. Could be a click-to-expand row, or a footnote, rather than a separate table. Not required for launch; add only if this scenario turns out to matter in practice.

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

Only needed if the finer-grained view from §4/§5 (catching a backing-model swap under one `service_id`) turns out to matter in practice.

| File | Change |
|---|---|
| `metering_service.py` / `model_breakdown()` | Add an additional query grouped by the `model` label (not `service_id`) against `telemetry_obsv_llm_tokens_processed_sum` — tokens only, since that's the only metric carrying this finer label |
| `schemas/metering.py` | Add an optional nested `real_model_breakdown` list on `ModelRow`, or a separate lightweight endpoint, if this is surfaced as a drill-down |

No changes to the shared metrics library are needed for this either — the `model` label already exists on the tokens histogram today.

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
| **New file** `components/metering/ModelConsumptionTab.tsx` | Clone of [`ServiceConsumptionTab.tsx`](frontend/simple-ui/src/components/metering/ServiceConsumptionTab.tsx) — same KPI cards + donut + table layout, same columns (Model / Requests / Tokens / Success % / Failure %) |
| [`components/metering/UsageDashboardPanels.tsx`](frontend/simple-ui/src/components/metering/UsageDashboardPanels.tsx) | Render `<ModelConsumptionTab>` when `subTab === METERING.SUB_TAB.MODEL`, in both the tenant and adopter panel components |

No new shared UI components are needed — `MeteringDonutChart`, `MeteringDataTable`, `MeteringSectionCard`, `MeteringAsyncState` are all already generic and reusable as-is.

---

## 10. Open questions to decide before/while building

1. **Where should this tab live?** As a new top-level sub-tab next to "Service Consumption" (like this doc assumes), or nested inside Service Consumption only when the LLM row is expanded/clicked? A top-level tab is simpler and matches the ask more directly.
2. **Should Tenant Admins see this too, or only Platform Admins?** Service Consumption is visible to both — recommend the same for consistency.
3. **Is the `service_id` grouping (§4) the right definition of "model" for this feature?** It matches how models are registered in `mm_services` and how tenants select them via the API, and it's what makes the full table possible without tracking changes. Worth confirming this matches what stakeholders picture when they say "agrinet, gemma, etc." — if they specifically mean the real backing model file rather than the registered service, that's the Phase 2 drill-down (tokens only) instead.
4. **Friendly model names (Phase 3)** — worth doing now, or fine to launch with raw `service_id` strings (e.g. `agrinet-model`) as-is?

---

## 11. Rough effort shape

- **Phase 1 (full model breakdown tab — Requests, Tokens, Success %, Failure %):** small — one new backend method + route + schema, one new frontend tab component + wiring, all reusing existing shared pieces and requiring no changes to the shared metrics library. Comparable in size to how Service Consumption itself was built.
- **Phase 2 (optional real-backing-model drill-down):** small, independent add-on — one extra query grouped by a label that already exists.
- **Phase 3 (friendly names):** small, independent, can be done anytime after Phase 1.
