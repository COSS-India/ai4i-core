# Feedback Service — Review

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
4. Support batch re-evaluation of historical traces.

## Internal correctness

The service compiles, the routes are wired through `create_inference_app`,
the SQLAlchemy model and Pydantic schemas line up, and the path layout
(`/api/v1/feedback/*` plus `/health`) is consistent. That said, several
behavioural defects mean it does not actually work end-to-end:

1. **Background evaluation uses the wrong DB session.**
   Routes acquire a tenant-scoped session via `get_tenant_db_session_factory()`
   and write the new `FeedbackMetric` into the tenant schema, but the
   background task pulls `request.app.state.db_session_factory` — the global,
   non-tenant session. The follow-up
   `select(FeedbackMetric).where(id == record_id)` runs against the public/
   shared schema and returns `None`, so PENDING records under a real tenant
   never transition to PASS/FAIL/ERROR. The same issue affects
   `_bg_batch_evaluate`. (`app/routes/feedback.py:139`,
   `app/routes/evaluation.py:75-90`).

2. **Auth dependency contradicts the schema.**
   Every route — including implicit telemetry (`POST /event`) and explicit
   user feedback (`POST /api/v1/feedback`) — is gated by `AdminRequired`.
   The Pydantic schema explicitly supports `feedback_source = "user"`, but
   end-users (and upstream inference services) cannot reach the endpoint
   without an admin JWT. Either the auth requirement needs to relax for the
   ingestion endpoints, or the design intent (admin-only) needs to be
   stated and the schema trimmed.

3. **`organization` is collapsed into `tenant_id`.**
   `_org_from_request` returns `tenant_id or "default"` and writes the same
   value to both `organization` and `tenant_id` columns. The model treats
   them as separate dimensions (and the indexes
   `ix_feedback_org_status` / `ix_feedback_org_task` exist for cross-tenant
   org-level queries), so the column is effectively unusable.

4. **Implicit-score state machine is one-shot and not idempotent.**
   - Once `ai_status` leaves `PENDING`, no further negative event can
     re-trigger evaluation, even if the running `implicit_score` keeps
     dropping.
   - `implicit_score` is accumulated but never read for any decision; only
     the *latest* event's `reward_score` is compared to the ±0.5 threshold.
   - Replays of the same telemetry event keep adding to `implicit_score`
     and `event_log`. There is no event id / dedup key.

5. **Sync wrapper around async background.**
   `_bg_evaluate` is `def`, not `async def`, so FastAPI runs it in the
   threadpool and the body calls `asyncio.run(...)`. Each invocation spins
   up a fresh event loop and httpx client (timeout 300 s). It works but
   serialises behind the threadpool and makes connection reuse impossible.

6. **`FeedbackStatusResponse` is missing fields the API needs.**
   It omits `created_at`, `event_log`, `feedback_source`, `organization`,
   and `tenant_id`. The `/latest` endpoint exposes an `organization`
   filter, but the response can't show which org a row belongs to.

7. **Brittle JSON parsing.**
   `_parse_json_object` and `_parse_json_array` use greedy `\{.*\}` /
   `\[.*\]` regexes. If the LLM emits stray braces (commentary, examples)
   the parse fails and the record silently lands in `ai_status="ERROR"`.

## Orchestration integration

This is where the service is most clearly broken.

1. **The database is never created.**
   - `services/feedback-service/.env.template` references
     `<FEEDBACK_DB_NAME>` and the root `env.template` adds
     `FEEDBACK_DB_NAME=...`, but neither
     `infrastructure/databases/migrations/postgres/alembic.ini`
     `version_locations` nor
     `infrastructure/.../alembic/migration_registry.py`
     (`DATABASE_ORDER` / `DATABASES`) registers a `feedback_db`. Alembic
     never sees the migration in
     `versions/feedback-service/001_create_feedback_tables.py`.
   - `scripts/migrate.sh` and `scripts/setup-env.sh` make no mention of
     the service. There is no provisioning path that creates
     `feedback_metrics`. Once the container starts, the first DB query
     will fail.

2. **No API gateway route.**
   `apisix.yaml`, `kong.yml`, and `nginx.conf` contain no entries for
   `/api/v1/feedback/*`. The service is reachable only via the host port
   `8100` published by docker-compose, not through the public gateway that
   every other service is exposed behind.

3. **No upstream producers.**
   None of `nmt-service`, `asr-service`, `tts-service`, `ocr-service`,
   `pipeline-service`, or `telemetry-service` import or call the feedback
   service. The implicit-event endpoint has zero clients in the repo, so
   the RLAIF telemetry pipeline does not exist end-to-end — only its
   sink does.

4. **Frontend integration is a stub.**
   `frontend/simple-ui/env.template` ships `NEXT_PUBLIC_ENABLE_FEEDBACK=false`
   but no UI code reads the flag, no rating widget exists, and there are
   no fetches to `/api/v1/feedback`.

5. **Compose dependencies are incomplete.**
   `feedback-service` only depends on `config-service` and `postgres`. With
   `AUTH_ENABLED=true` and `JWKS_URL=http://auth-service:8081/...`, the
   service needs `auth-service` to be reachable for any authenticated
   request to resolve. Cold starts will produce JWKS fetch errors until
   `auth-service` happens to come up.

6. **LLM judge has no provider in compose.**
   `.env.template` defaults `LLM_JUDGE_URL=http://ollama:11434/api/generate`
   but there is no `ollama` (or compatible) container in either
   `docker-compose.yml` or `docker-compose-local.yml`. Out of the box,
   every triggered evaluation falls into the exception branch and the
   record goes to `ai_status="ERROR"` with `payload.error` set.

7. **No tests.**
   `tests/integration/` and `tests/e2e/` cover NMT, ASR, TTS, the API
   gateway, auth flows, and the websocket layer — nothing for feedback.
   There is no fixture, contract test, or smoke test for the service.

## Verdict

In its current state the service is well structured at the file level but
is not operationally wired in:

- Out of the box it cannot serve traffic (no DB schema, no gateway route).
- Even if traffic reached it, every tenant-scoped record stays PENDING
  (background-task session bug).
- Even if the session bug is fixed, the LLM judge has no provider, so the
  records would land in ERROR.
- And no producer in the platform is sending it any events anyway.

## Recommended fix order

1. Register `feedback_db` in `migration_registry.py` and add the
   `feedback-service` path to `alembic.ini`'s `version_locations`. Add the
   service to `scripts/migrate.sh` so the table is actually created.
2. Make the background `_bg_evaluate` use a tenant-scoped session (or pass
   the tenant schema into the task and `SET search_path` before querying).
3. Decide auth posture: if implicit telemetry is meant to come from
   inference services, expose `/event` (and probably `POST /`) with a
   service-account scope, not `AdminRequired`.
4. Add `auth-service` (and the chosen LLM judge) to `depends_on` /
   compose, and add an APISIX route for `/api/v1/feedback/*`.
5. Stand up at least one producer: have `pipeline-service` (or each
   inference service) emit `/event` calls when corrections / retries
   happen. Without this, the RLAIF loop is dead.
6. Replace the `organization == tenant_id` shortcut, expose the missing
   columns in `FeedbackStatusResponse`, and add an event id for
   idempotent ingestion.
7. Add at least an integration test that posts an event, asserts the
   record exists, and verifies the LLM-judge branch using a stub.
