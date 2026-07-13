# Updating With Tracing + Pay-Per-Use Billing

This follows the same structure and step numbering as `docs/SETUP_GUIDE.md` — services are still started
one at a time, in the same order. The difference: every fix from `TRACE-LOGS-FIX-RUNBOOK.md` and
`BILLING-PIPELINE-FIX-NOTES.md` is folded directly into the step of the service it belongs to (its `.env`
edit, its `requirements.txt` edit, its code edit — all applied *before* that service's venv is created or
it's started for the first time). Follow it top to bottom once; nothing needs a second pass or a restart.

As of the current codebase, most of those fixes already ship as defaults in the templates/code
(`fluent-bit.conf`, the `.env.template` files, `requirements.txt`, `llmService.ts`) — so the manual edit
steps for those are gone below. What's left is what still genuinely depends on your environment (real
LLM endpoints, tier/tenant/pricing data) or is a one-time bootstrap action.

**Run model:** infrastructure (PostgreSQL, Redis, Kafka, observability stack) runs in Docker; the
application services (`auth-service`, `platform-core-service`, `inference-service`, `kafka-consumers`) run
natively on the host.

## Prerequisites

- Docker + Docker Compose
- **Python 3.11**, callable as `python3.11` (plain `python3` may resolve to a newer interpreter that's
  missing packages the migration tooling needs — e.g. `sqlalchemy`)
- Node.js 18+
- Git

## Step 1: Clone the Repository

```bash
git clone --branch <release-tag> git@github.com:COSS-India/ai4i-core.git
cd ai4i-core
```

## Step 2: Create the Root Environment File

```bash
cp env.template .env
```

Open `.env` and fill in:

```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
REDIS_PASSWORD=changeme
```

Also fix this one — the template ships this blank, and it breaks billing later if left as-is:

```bash
PLATFORM_CORE_DB=ai4iplatform_core
```

And since this setup uses the LLM task type:

```bash
LLM_UPSTREAM_BASE_URL="<enter llm url>"
```

## Step 3: Generate All Service Environment Files

```bash
./scripts/setup-env.sh
```

Creates `.env` for `auth-service`, `platform-core-service`, `inference-service`, `kafka-consumers`,
`frontend/simple-ui`, and the Alembic migration tool, substituting the values from Step 2.

## Step 4: Start Infrastructure Services (Full Observability)

### Step 4.1: Start the full observability stack

```bash
docker compose -f docker-compose-local.yml \
  --profile logging --profile observability \
  up -d \
  postgres redis \
  zookeeper kafka \
  opensearch opensearch-init \
  prometheus alertmanager grafana node-exporter \
  fluent-bit opensearch-dashboards
```

Wait for all 11 containers to become **healthy** (`opensearch-init` shows `Exited (0)` — that's expected):

```bash
docker compose -f docker-compose-local.yml ps
```

### Step 4.2: Create the OpenSearch Dashboards index patterns

Nothing in OpenSearch Dashboards is browsable until an index pattern exists. This only needs
`opensearch-dashboards` up, so do it now rather than waiting until traces actually start flowing.

Run the script instead of raw `curl` calls — it polls until OpenSearch Dashboards is reachable and is
safe to re-run (an already-existing pattern is treated as success):

```bash
./scripts/setup-osd-index-patterns.sh
```

## Step 5: Initialize Databases

### Step 5.1: Install Migration Framework Dependencies

```bash
cd infrastructure/databases
python3.11 -m pip install -r requirements.txt
cd ../..
```

### Step 5.2: Run All Migrations

```bash
./scripts/migrate.sh all upgrade
```

Creates `ai4iplatform_auth`, `ai4iplatform_core`, `ai4i_platform_db`, applies every migration, and seeds
the default admin (`admin@ai4inclusion.org` / `ADMIN_PASSWORD`), default roles, and permissions.

### Step 5.3 (Optional): Set pricing on `mm_services` — only if it's missing

Check first — pricing may already be seeded from a previous run or migration, so don't assume it needs
fixing:

```bash
docker exec ai4v-postgres psql -U postgres -d ai4iplatform_core -c \
  "SELECT service_id, name, task_type, cost_per_unit, unit_rate, unit_size FROM public.mm_services;"
```

Only continue if `cost_per_unit` / `unit_rate` / `unit_size` come back `NULL` — that means nothing can
ever be billed until they're set. If they're already populated, skip the rest of this step.

Ask the user what price to set before running this — do not assume ₹20/unit:

```bash
docker exec ai4v-postgres psql -U postgres -d ai4iplatform_core -c \
  "UPDATE public.mm_services SET cost_per_unit = <enter_cost_per_unit>, unit_size = <enter_unit_size>, unit_rate = <enter_unit_rate>;"
```

This has no `WHERE` clause and sets the price on **every** service row by design (matches the source
runbook) — scope it to one `service_id` if that's not what you want.

Separately, check the LLM row's `task_type` — only fix it if it comes back blank. Cost still calculates
without it, but quota tracking (`ppu_quota_usage`) silently never updates, because it can't match
`ppu_tier_quotas.inference_name` (which expects the literal string `llm`):

```bash
docker exec ai4v-postgres psql -U postgres -d ai4iplatform_core -c \
  "SELECT service_id, task_type FROM mm_services WHERE service_id='d4f4dd9d87b6e821302938974af23dac';"
```

If `task_type` isn't already `llm`:

```bash
docker exec ai4v-postgres psql -U postgres -d ai4iplatform_core -c \
  "UPDATE mm_services SET task_type='llm' WHERE service_id='d4f4dd9d87b6e821302938974af23dac';"
```

## Step 6: Auth Service

### Step 6.1: Install Dependencies and Run

```bash
cd services/auth-service
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

Wait for `Application startup complete`. Verify at **http://localhost:8081/docs**.

> Leave this running in its own terminal. Open a new terminal for Step 7.

## Step 7: Platform Core Service

### Step 7.1: Install Dependencies and Run

```bash
cd services/platform-core-service
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload
```

Wait for `Application startup complete`. Verify at **http://localhost:8095/docs**.

> Leave this running in its own terminal. Open a new terminal for Step 7.2.

### Step 7.2: Create a PPU tier and assign it to a tenant

**Not covered by any of the source runbooks** — they all assume a tier and tenant assignment already
exist. A fresh database has empty `ppu_tiers`, `ppu_tenant_tier_assignments`, and `ppu_tier_quotas` tables,
so even with Step 5.3's pricing applied there is nothing to bill against yet. This needs both
Step 6 (auth-service) and Step 7.1 (platform-core-service) already running.

Ask the user for the tier and tenant details before creating anything — do not assume defaults:

- Tier name and description
- Quota task type(s) and limit(s)
- Tenant ID to assign the tier to
- Budget amount
- Effective date range (start / end)

Once you have those, log in as the seeded admin (`admin@ai4inclusion.org` / `ADMIN_PASSWORD`) against
auth-service to get a token, create the tier via `POST /api/v1/pay-per-use/tier` on platform-core-service,
then assign it to the tenant via `POST /api/v1/pay-per-use/tenant/tier`.

## Step 8: Inference Service

### Step 8.1: Fix the `.env` — real LLM endpoints

The generated `.env` doesn't know the real LLM upstream endpoints yet (Kafka export ships **on** by
default already, so tracing needs no manual edit here). Edit `services/inference-service/.env`:

Ask the user for the real LLM upstream endpoint(s) before filling these in — do not assume any default
host or IP:

```bash
LLM_DEFAULT_ENDPOINT="<enter llm default endpoint>"
LLM_MODEL_ENDPOINTS={"google/gemma-4-E4B-it":"<enter endpoint for google/gemma-4-E4B-it>","agrinet-model":"<enter endpoint for agrinet-model>"}
```

### Step 8.2: Install Dependencies and Run

```bash
cd services/inference-service
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

Confirm the startup log includes both of these — this is the actual proof tracing is working, not just
that the service started:

```
✓ Kafka span exporter initialized: topic=traces, servers=localhost:9093
✅ Tracing initialized for tracer: ...
```

If the Kafka exporter line is missing, check that `opentelemetry-exporter-otlp-proto-grpc` (and the
matching `opentelemetry-*` package set) actually installed from `requirements.txt` — tracing fails
**silently** if it's missing, with no error or warning.

Verify at **http://localhost:8090/docs**.

> Leave this running in its own terminal. Open a new terminal for Step 9.

## Step 9: Kafka Consumers (Pay-Per-Use Billing)

Not part of the original setup guide's service list — this is the consumer that reads trace spans off
Kafka and deducts tenant budget. It has to run for any billing to happen at all.

### Step 9.1: Install Dependencies and Run

```bash
cd services/kafka-consumers
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Confirm the log shows a clean `Consumer started | topics=['traces'] ...` with no traceback.

> Leave this running in its own terminal. Open a new terminal for Step 10.

## Step 10: Frontend (Simple UI)

`frontend/simple-ui/src/services/llmService.ts` already maps the Gemma chat model to the real, priced
`llm-indic-prod` service (`d4f4dd9d87b6e821302938974af23dac` — the row from Step 5.3) — no edit needed.

### Step 10.1: Install Dependencies and Run

```bash
cd frontend/simple-ui
npm install
npm run dev
```

The UI is available at **http://localhost:3000**.

## Step 11: Access the Platform

| Service / Tool | URL | Notes |
|---|---|---|
| Auth Service | http://localhost:8081/docs | Runs natively |
| Platform Core Service | http://localhost:8095/docs | Runs natively |
| Inference Service | http://localhost:8090/docs | Runs natively |
| Kafka Consumers | — (no HTTP endpoint) | Runs natively — check `kafka-consumer.log` |
| Simple UI | http://localhost:3000 | Runs natively (Next.js) |
| Prometheus | http://localhost:9090 | Docker |
| Alertmanager | http://localhost:9095 | Docker |
| Grafana | http://localhost:3001 | Docker |
| OpenSearch Dashboards | http://localhost:5602 | Docker |

### Default Credentials

- **Email**: `admin@ai4inclusion.org`
- **Password**: `ADMIN_PASSWORD`

## Step 12: Verify It Works

### Step 12.1: Direct API call (gateway-less, manual identity headers)

```bash
curl -X POST http://localhost:8090/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: $(python3 -c 'import uuid; print(uuid.uuid4().hex)')" \
  -H "X-Tenant-Id: 1" \
  -d '{"model":"google/gemma-4-E4B-it","serviceId":"d4f4dd9d87b6e821302938974af23dac","messages":[{"role":"user","content":"say hi in one word"}],"stream":false}'
```

### Step 12.2: Real frontend flow (real login → Next.js proxy → real chat)

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))")

curl -X POST http://localhost:3000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"model":"google/gemma-4-E4B-it","serviceId":"d4f4dd9d87b6e821302938974af23dac","messages":[{"role":"user","content":"..."}],"stream":false}'
```

### Step 12.3: Confirm billing and tracing actually happened

```bash
docker exec ai4v-postgres psql -U postgres -d ai4iplatform_core -c \
  "SELECT tenant_id, available_balance FROM ppu_tenant_tier_assignments WHERE tenant_id='1';"
```

`available_balance` should have dropped by `tokens billed × ₹20/unit` after each call above. Also check:

```bash
tail -f services/kafka-consumers/kafka-consumer.log   # look for "Balance deducted" / "Quota usage upserted"

curl -s "http://localhost:9204/traces-$(date +%Y.%m.%d)/_search" -H "Content-Type: application/json" -d \
  '{"size":1,"sort":[{"@timestamp":{"order":"desc"}}],"query":{"match":{"name":"ai-inference"}}}'
```

## Troubleshooting

### Port 3000 already in use

Usually a stray `next-server` process left running from a previous session, not a real conflict:

```bash
lsof -i :3000   # or: ss -tlnp | grep 3000
kill <pid>
```

### Fluent Bit still shows "Subscribed topic not available"

`fluent-bit.conf` ships with `Topics traces` by default — if you still see this, the container's config
doesn't match (e.g. a stale image, or a local edit reverted it). Confirm the `[INPUT]` block with
`Name kafka` reads:

```
Topics            traces
```

Then:

```bash
docker restart ai4v-fluent-bit
docker logs ai4v-fluent-bit --tail 20
```

### `platform-core-service` logs `Permission denied` on `alertmanager.yml` every 60s

`infrastructure/alertmanager/alertmanager.yml` was previously written by a Docker container running as
`root`; the native service can't overwrite it. Non-blocking, but silence it with:

```bash
sudo chown $USER infrastructure/alertmanager/alertmanager.yml
```

### `./scripts/migrate.sh` fails with `ModuleNotFoundError: No module named 'sqlalchemy'`

Plain `python3` resolved to a different interpreter than the one you `pip install`ed into. Force it:

```bash
export PYTHON_BIN=python3.11
```

## Stopping / Starting Over

```bash
docker compose -f docker-compose-local.yml down -v   # stop infra + wipe volumes
```

Then `Ctrl+C` each native service (`auth-service`, `platform-core-service`, `inference-service`,
`kafka-consumers`, frontend).
