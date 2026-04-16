# Feedback Service — Review (v3)

Scope: `services/feedback-service/` plus all touch points that connect it to
the rest of the platform (compose, gateways, alembic, upstream services,
frontend).

## What the service is supposed to do

Per its own description, an RLAIF pipeline:

1. Ingest implicit telemetry events (corrections, retries, dwell, etc.) from
   the inference services (NMT/ASR/TTS/OCR) and accumulate a reward score
   per `trace_id`.
2. When the running reward crosses a threshold, fire an LLM-as-judge
   evaluation (Ollama by default) and persist a PASS/FAIL verdict + error
   taxonomy.
3. Accept explicit user feedback (rating + text), human corrections (golden
   pair for RLHF), and admin overrides.
4. Support batch re-evaluation of historical traces — now via a pull-based
   model that reads directly from the NMT database.


## Issues fixed since v1 review

1. **Background evaluation tenant awareness** — FIXED.
   `_bg_evaluate` and `_bg_batch_evaluate` now receive `schema_name` from
   `request.state.tenant_schema` and execute
   `SET search_path TO "{schema_name}", public` before querying.
   PENDING records under a real tenant will now correctly transition.

2. **Auth split** — FIXED.
   `auth.py` now exports both `AuthRequired` (any valid JWT) and
   `AdminRequired` (ADMIN role). Ingestion endpoints (`POST /event`,
   `POST /`) use `AuthRequired`; query, correction, batch, and override
   endpoints use `AdminRequired`.

3. **`organization` no longer collapsed into `tenant_id`** — FIXED.
   `_org_from_request` now derives organization from the JWT email domain
   (`email.split("@")[1].lower()`), keeping it semantically distinct from
   the tenant_id column.

4. **`FeedbackStatusResponse` expanded** — FIXED.
   Now includes `organization`, `tenant_id`, `feedback_source`, `rating`,
   `implicit_score`, `event_log`, `created_at`, and `updated_at`.

5. **Database registered in alembic** — FIXED.
   `alembic.ini` `version_locations` now includes `feedback-service`.
   `migration_registry.py` has `feedback_db` in `DATABASE_ORDER` and a
   `DatabaseSpec` with `_load_feedback_metadata`.
   `scripts/migrate.sh` also includes `feedback_db`.

6. **API gateway routes added** — FIXED.
   APISIX has a full route for `/api/v1/feedback/*` with forward-auth,
   CORS, rate-limiting, correlation-ID injection, and response headers.
   Nginx also has a `proxy_pass` entry.
   (Kong still has no route — see remaining items below.)

7. **docker-compose `depends_on`** — FIXED.
   `auth-service: condition: service_started` added to both compose files.

8. **Batch evaluation redesigned (new `nmt_reader.py`)** — IMPROVED.
   `BatchProcessRequest` now takes `limit`/`offset`/`skip_evaluated`
   instead of a caller-supplied items array. The service pulls directly
   from the NMT database (`nmt_requests JOIN nmt_results`), creating
   FeedbackMetric records for un-evaluated rows and queuing them for LLM
   evaluation. The SQL column names (`source_text`, `translated_text`,
   `source_language`, `target_language`, `model_id`) are verified to match
   the NMT service's ORM model.

9. **`.env.template` updated** — FIXED.
   Now includes `NMT_DB_URL` for the read-only NMT database connection and
   clarifies the `DATABASE_URL` as the feedback service's own store.

10. **`schemas/__init__.py` exports** — FIXED.
    All schema classes are now re-exported.


## Issues fixed since v2 review

11. **Host port conflict** — FIXED.
    `multi-tenant-service` was already mapped to host port `8100`. Both
    `docker-compose.yml` and `docker-compose-local.yml` now map
    feedback-service to `8106:8100`. Internal service-to-service traffic
    (`http://feedback-service:8100`) is unaffected.

12. **SQL injection in `SET search_path`** — FIXED.
    Both `feedback.py` and `evaluation.py` now include
    `_SAFE_SCHEMA_RE = re.compile(r'^[a-z0-9_]+$')` and a
    `_validate_schema()` helper. The background async functions validate
    the schema name before interpolating it into the SQL statement;
    malformed names are rejected with a warning log and the SET is skipped.

13. **Ollama added to docker-compose** — FIXED.
    `docker-compose.yml` includes an `ollama` service under the `feedback`
    profile (`docker compose --profile feedback up -d`). Uses the `ollama`
    network alias that `.env.template` already expects.
    Note: only present in `docker-compose.yml`, not `docker-compose-local.yml`.

14. **Frontend implicit-event integration** — FIXED (previously missed).
    `feedbackService.ts` defines the `ImplicitAction` type
    (`COPY_TRANSLATION`, `COPY_SOURCE`, `CLEAR_RESULTS`, `RETRANSLATE`)
    with calibrated reward scores (+0.7, +0.1, -0.3, -0.5). The
    `sendImplicitEvent` function POSTs to the feedback `/event` endpoint
    (skipped for anonymous users). `useNMT.ts` exposes a
    `sendFeedbackEvent` callback, and `nmt.tsx` hooks all four implicit
    signals to the corresponding user actions (copy translation, copy
    source, clear results, re-translate). This means the NMT page is a
    live producer of implicit telemetry events.


## Remaining issues

### Internal (code-level)

1. **Implicit-score state machine is one-shot and not idempotent.**
   Once `ai_status` leaves `PENDING`, no further negative event can
   re-trigger evaluation, even if the running `implicit_score` keeps
   dropping. `implicit_score` is accumulated but never read for any
   decision — only the latest event's `reward_score` is compared to the
   ±0.5 threshold. There is also no event id / dedup key, so replays keep
   adding to the score and log. (Lower priority — design decision.)

2. **`nmt_reader.py` has no schema / search_path awareness.**
   The raw SQL in `fetch_nmt_records` runs against the default search_path
   of the NMT database connection. If the NMT tables live in a
   tenant-specific schema, the query will return nothing. This should
   either accept a schema parameter or document that it only works with
   public-schema NMT deployments.

3. **Sync wrapper still spins up a fresh event loop per background task.**
   `_bg_evaluate` / `_bg_batch_evaluate` are sync `def` calling
   `asyncio.run(...)`. This creates and tears down an event loop + httpx
   client per invocation. It works correctly but is heavy. (Lower priority.)

4. **Brittle JSON parsing.**
   `_parse_json_object` and `_parse_json_array` use greedy `\{.*\}` /
   `\[.*\]` regexes. If the LLM emits stray braces the parse fails and
   the record silently lands in `ai_status="ERROR"`. (Lower priority.)

### Orchestration

5. **Ollama missing from `docker-compose-local.yml`.**
   The ollama service was added to `docker-compose.yml` under the
   `feedback` profile, but not to `docker-compose-local.yml`. Local
   dev environments will still lack an LLM judge unless pointed at an
   external instance.

6. **Frontend feature flag is still `false`.**
   `NEXT_PUBLIC_ENABLE_FEEDBACK=false` in `env.template`. The code behind
   it works (verified), but new deployments will ship with the flag off by
   default. This is presumably intentional (opt-in), but worth noting so
   it doesn't get forgotten in deployment checklists.

7. **Kong gateway not configured.**
   APISIX and nginx have routes; kong.yml does not. If Kong is the
   fallback or secondary gateway in any deployment, traffic won't reach
   the feedback service through it.

8. **No tests.**
   `tests/integration/` and `tests/e2e/` cover NMT, ASR, TTS, the API
   gateway, auth flows, and websockets — nothing for feedback. There is
   no fixture, contract test, or smoke test for the service.

9. **No implicit-event producers for ASR/TTS/OCR.**
   The NMT frontend is now a live producer of implicit events, which
   closes the "no producers" gap for NMT. The ASR, TTS, and OCR pages
   (if they exist) do not yet emit feedback events. The batch evaluation
   path also only covers NMT. (Lower priority — NMT-first is reasonable.)


## Verdict (v3)

The feedback service is now operationally viable for NMT workflows:

- The database schema is provisioned via alembic.
- APISIX and nginx expose the routes.
- Auth is correctly tiered (any-JWT for ingestion, ADMIN for admin ops).
- Background evaluation is tenant-aware and SQL-injection-safe.
- The NMT frontend emits all four implicit signals with calibrated rewards.
- Batch evaluation self-serves from the NMT database.
- Ollama is available via the `feedback` docker-compose profile.

The remaining items are either lower-priority design decisions (state
machine semantics, JSON parsing robustness), coverage gaps for non-NMT
services, or missing test infrastructure. None are blockers to running the
NMT feedback loop end-to-end.

### Recommended next steps (priority order)

1. Add ollama to `docker-compose-local.yml` so local dev matches prod.
2. Add at least one integration test: post an event, verify the record,
   mock the LLM judge, assert the PASS/FAIL transition.
3. Decide whether `nmt_reader.py` needs tenant-schema support or is
   intentionally public-schema only, and document accordingly.
4. Add the Kong route if Kong is used in any deployment.
5. Extend implicit-event hooks to ASR/TTS/OCR pages when they're ready.
