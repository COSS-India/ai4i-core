# Local setup guide — Docker Compose + AI4I-Orchestrate

Complete walkthrough for running **platform infra with this Docker Compose pack** and **application services natively** on Linux (same runtime model as ai4i-core’s end-to-end local setup).

| Layer | How it runs |
|-------|-------------|
| Infra (Postgres, Redis, …) | **Docker Compose** (this folder) |
| Auth / platform-core / inference | **Native uvicorn** on the host — **one service per terminal** |
| Simple UI (optional) | **Native Next.js** on the host |
| NMT / other models (optional) | **Separate Docker** (e.g. model-hosting Triton) — not started by this compose |

> **OS:** Linux only (Ubuntu tested).  
> **Sizing:** [MINIMAL-INFRA-REQUIREMENTS.md](MINIMAL-INFRA-REQUIREMENTS.md)

### One-shot reset → NMT E2E (optional)

From a host terminal where Docker works:

```bash
export AI4I_LOCAL=/path/to/cloned-repos
export HF_TOKEN=hf_...   # HuggingFace Read token (IndicTrans2 access)
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/reset-and-setup-local.sh"
```

This tears down Compose volumes/apps/NMT, rebuilds core infra, migrates, starts services, builds/runs Triton NMT, patches the NMT endpoint, and curls a Hindi translation via inference.

---

## Table of contents

1. [System prerequisites](#1-system-prerequisites)
2. [Architecture](#2-architecture)
3. [Workspace layout](#3-workspace-layout)
4. [Part A — Local NMT (Triton)](#part-a--local-nmt-triton)
5. [Part B — Docker Compose infra](#part-b--docker-compose-infra)
6. [Part C — Environment files & migrations](#part-c--environment-files--migrations)
7. [Part D — Application services (one by one)](#part-d--application-services-one-by-one)
8. [Part E — Verify the stack](#part-e--verify-the-stack)
9. [Part F — Frontend (optional)](#part-f--frontend-optional)
10. [Part G — Optional Compose profiles](#part-g--optional-compose-profiles)
11. [Part H — Wire NMT to the platform](#part-h--wire-nmt-to-the-platform)
12. [Port reference](#port-reference)
13. [Stopping and restarting](#stopping-and-restarting)
14. [Troubleshooting](#troubleshooting)

---

## 1. System prerequisites

### Hardware (app-minimal: Postgres + Redis + host apps)

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 8 GB | 16 GB+ (more if NMT / full Compose core) |
| Disk | 20 GB free | 40 GB+ (NMT image alone is large) |
| CPU | x86_64 | Multi-core |
| GPU | Not required | — |

For full core / monitoring / logging RAM and disk, see [MINIMAL-INFRA-REQUIREMENTS.md](MINIMAL-INFRA-REQUIREMENTS.md).

### Software

| Tool | Required for |
|------|----------------|
| Docker Engine 24+ & Compose v2.20+ | Part A (NMT) and Part B (Compose) |
| Git | Clone repos |
| HuggingFace Read token | Part A — gated IndicTrans2 weights |
| **Python 3.11+** (`python3.11`) + pip | Parts C–D — **required**; `ai4i-core` on PyPI needs `requires-python >= 3.11` |
| Node.js **18+** & npm | Part F only |

```bash
docker --version
docker compose version
docker ps
git --version
python3.11 --version       # must print 3.11.x or newer (NOT system python3 if that is 3.10)
python3.11 -m pip --version
node --version             # optional
```


#### HuggingFace account & token (required for Part A NMT)

IndicTrans2 model weights are **gated**. Before building NMT:

1. Create an account at [huggingface.co](https://huggingface.co)
2. Open each model page and click **“Agree and access repository”**:
   - [indictrans2-en-indic-dist-200M](https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M)
   - [indictrans2-indic-en-dist-200M](https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M)
   - [indictrans2-indic-indic-dist-320M](https://huggingface.co/ai4bharat/indictrans2-indic-indic-dist-320M)
3. Create a **Read** token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (`hf_...`). **Keep it secret** — never commit it.

> **Important:** On many Ubuntu hosts `python3` is still **3.10**. Do **not** use that for service venvs — `pip install ai4i-core==…` fails with `No matching distribution found`. Always create venvs with **`python3.11`** (or newer).

---

## 2. Architecture

Applications are **not** started by Docker Compose. Infra runs in Docker; backends and UI start **one by one** on the host.

### 2.1 Runtime architecture (request path)

Same layering as the ai4i-core end-to-end local architecture:

```
┌──────────────────────────────────────────────────────────────────┐
│  UI LAYER  (native Next.js — start last, optional)               │
│  Simple UI  :3000                                                │
│    └─ /api/v1/* → pages/api/v1/[...proxy].ts                     │
│         path routing + forward-auth (/api/v1/auth/validate)      │
│         injects X-User-ID / X-Tenant-ID / X-Permission-IDs       │
└───────────────────────────────┬──────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────┐
│  BACKEND SERVICES  (native uvicorn — start one per terminal)     │
│  1) auth-service :8081                                           │
│  2) platform-core :8095                                          │
│  3) inference :8090                                              │
└───────────────┬───────────────────────────────┬──────────────────┘
                │                               │
                ▼                               ▼
┌───────────────────────────────┐   ┌──────────────────────────────┐
│  SYSTEM / RECORDS  (Compose)  │   │  AI MODEL LAYER  (optional)  │
│  PostgreSQL  :5432            │   │  e.g. indictrans (Triton)    │
│  Redis       :6379            │   │  :8000  /v2/models/nmt/infer │
└───────────────────────────────┘   └──────────────────────────────┘
```

### 2.2 Compose infra layers

```
┌──────────────────────────────────────────────────────────────────┐
│  COMPOSE CORE (required — bring up in order below)               │
│  1) postgres :5432   redis :6379                                 │
│  2) kafka :9092   etcd :2379   apisix :9080 / admin :9180        │
└──────────────────────────────────────────────────────────────────┘
         │ optional LAST — monitoring │ optional LAST — logging
         ▼                            ▼
┌────────────────────────┐    ┌────────────────────────────────────┐
│ prometheus :9090       │    │ opensearch :9200                   │
│ grafana :3001          │    │ dashboards :5601                   │
│ alertmanager :9095     │    │ fluent-bit                         │
│ node-exporter :9100    │    └────────────────────────────────────┘
│ kafka-exporter :9308   │
└────────────────────────┘
```

**Required core:** Postgres, Redis, Kafka, etcd, APISIX.  
**Optional add-ons (last):** `--profile monitoring`, `--profile logging`.

### 2.3 Startup order (exact flow)

```
1. (recommended)    →  Part A — NMT Triton        :8000   (build/run; direct curl)
2. Docker Compose   →  postgres + redis                         (healthy)
3. Docker Compose   →  kafka (+ kafka-init) + etcd + apisix     (healthy)
4. setup-env.sh     →  per-service .env files
5. migrate.sh       →  create/upgrade app databases
6. Terminal 1       →  auth-service      :8081
7. Terminal 2       →  platform-core     :8095
8. Terminal 3       →  inference         :8090
9. (optional)       →  Simple UI         :3000
10. Part H          →  PATCH NMT endpoint + inference/UI test
11.(optional LAST)  →  --profile monitoring and/or --profile logging
```

Do **not** start inference before auth/platform-core are up if you rely on shared secrets / catalogue data; follow Parts C → D in order. NMT (Part A) can run before Compose; wire it to the platform in Part H after apps are up.

---

## 3. Workspace layout

Set a workspace variable (use it in every new terminal):

```bash
export AI4I_LOCAL=~/ai4i-local-setup   # adjust if your clone path differs
echo "$AI4I_LOCAL"
```

Expected layout:

```
~/ai4i-local-setup/
├── ai4i-core/
│   ├── services/
│   │   ├── auth-service/
│   │   ├── platform-core-service/
│   │   └── inference-service/
│   ├── frontend/simple-ui/
│   ├── scripts/migrate.sh
│   └── docker-compose/              # this folder
│       ├── docker-compose.yml
│       ├── .env.example
│       ├── SETUP-GUIDE.md           # this file
│       └── scripts/setup-env.sh
└── model-hosting/                   # separate repo — required for Part A NMT
    └── nmt-triton/                  # IndicTrans2 on Triton (CPU)
```

**NMT is not inside `ai4i-core`.** Clone the **`model-hosting`** repository next to `ai4i-core` (same workspace). Part A builds from `model-hosting/nmt-triton/`.

Clone **both** repositories into `$AI4I_LOCAL`:

```bash
mkdir -p "$AI4I_LOCAL"
cd "$AI4I_LOCAL"

# Platform — use the release tag your team uses (see GitHub Releases)
git clone --branch <release-tag> git@github.com:COSS-India/ai4i-core.git

# Model hosting — NMT Triton project (required for Part A / local translation E2E)
# https://github.com/COSS-India/model-hosting
git clone -b feat/nmt-local-setup git@github.com:COSS-India/model-hosting.git
```

| Repository | Ref | Purpose |
|------------|-----|---------|
| [`ai4i-core`](https://github.com/COSS-India/ai4i-core) | release tag | Platform + this Compose pack |
| [`model-hosting`](https://github.com/COSS-India/model-hosting) | `feat/nmt-local-setup` | **`nmt-triton/`** — CPU IndicTrans2 for local NMT |

```bash
ls "$AI4I_LOCAL/model-hosting/nmt-triton/Dockerfile"   # must exist before Part A
```

---

## Part A — Local NMT (Triton)

This is the **simple model to host locally** for an end-to-end inference test (same idea as the former end-to-end guide). It is **CPU NMT (IndicTrans2 on Triton)** — not LLM/chat. You can skip Part A if you only need Compose + apps without a model; for a real translation E2E, complete Part A **before** or in parallel with Compose, then [Part H](#part-h--wire-nmt-to-the-platform) after apps are up.

| Item | Value |
|------|--------|
| Repo | `model-hosting` (`nmt-triton/`) |
| Container | `indictrans` |
| Port | `8000` (HTTP), `8002` (metrics) |
| Seeded NMT `serviceId` | `de9a4570f8c14f6859cb79c1934a4db9` |

**Requirements:** ~16 GB+ RAM recommended, ~40 GB+ free disk (image ~18 GB + model cache), HuggingFace **Read** token with access to the gated IndicTrans2 repos (see [§1](#1-system-prerequisites)).

### A1. Verify NMT project files

```bash
cd "$AI4I_LOCAL/model-hosting/nmt-triton"
ls -la Dockerfile models/nmt/config.pbtxt models/nmt/1/model.py
```

**Expected:** `Dockerfile`, `models/nmt/config.pbtxt`, `models/nmt/1/model.py`.

### A2. Build the image

From inside `nmt-triton/` (the trailing `.` is required):

```bash
cd "$AI4I_LOCAL/model-hosting/nmt-triton"
docker build -t nmt-triton-cpu .
```

**Expected:** `Successfully tagged nmt-triton-cpu:latest` (first build takes several minutes and ~18 GB).

### A3. Run the container

Replace `hf_your_token_here` with your HuggingFace Read token:

```bash
docker run -d \
  -p 8000:8000 -p 8002:8002 \
  -v hf-cache:/cache \
  -e HF_TOKEN=hf_your_token_here \
  --name indictrans \
  nmt-triton-cpu
```

| Flag | Purpose |
|------|---------|
| `-p 8000:8000` | Triton HTTP API |
| `-p 8002:8002` | Triton metrics |
| `-v hf-cache:/cache` | Persist downloaded models across restarts |
| `-e HF_TOKEN=...` | Required on first run to download gated models |

### A4. Verify NMT is healthy

```bash
docker ps --filter name=indictrans
docker logs indictrans 2>&1 | tail -20
# Wait for: Started HTTPService at 0.0.0.0:8000

curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/v2/health/ready
# Expected: HTTP 200
```

CUDA/GPU warnings at startup are **normal on CPU-only machines**.

### A5. Test direct translation

```bash
curl -X POST http://localhost:8000/v2/models/nmt/infer \
  -H "Content-Type: application/json" \
  -d '{"inputs":[
    {"name":"INPUT_TEXT","shape":[1,1],"datatype":"BYTES","data":["Hello, how are you?"]},
    {"name":"INPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["en"]},
    {"name":"OUTPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["hi"]}]}'
```

Expect Hindi in `outputs[].data` (e.g. `नमस्ते, आप कैसे हैं?`). **The first call may take 1–3 minutes** while weights download into `hf-cache`.

> Prefer finishing this direct curl successfully before relying on platform inference (Part H).

**Stop NMT (later):** `docker stop indictrans` (remove with `docker rm indictrans` if recreating).

---

## Part B — Docker Compose infra

All compose commands run from **`ai4i-core/docker-compose/`**.

### B1. Create `.env`

```bash
cd "$AI4I_LOCAL/ai4i-core/docker-compose"
cp .env.example .env
```

Defaults match a typical local app stack:

| Variable | Default |
|----------|---------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | `postgres` / `postgres` |
| `POSTGRES_DB` | `ai4i_platform_db` |
| `REDIS_PASSWORD` | `changeme` |
| `KAFKA_EXTERNAL_PORT` | `9092` |

Edit `.env` if those ports or passwords conflict on your machine.

### B2. Bring up core infra (in order)

**Step 1 — Postgres + Redis:**

```bash
docker compose up -d postgres redis
docker compose ps
```

Expected: `ai4i-postgres` and `ai4i-redis` are **Up (healthy)**.

Init creates databases `ai4iplatform_auth` and `ai4iplatform_core` on first Postgres boot.

**Step 2 — Kafka + etcd + APISIX** (required before setup-env / apps for the full platform flow):

```bash
docker compose up -d kafka kafka-init etcd apisix
docker compose ps
```

Expected: `ai4i-kafka`, `ai4i-etcd`, `ai4i-apisix` **Up (healthy)**; `ai4i-kafka-init` exits **0**.

Equivalent one-shot for all core services: `docker compose up -d` (still wait until Postgres/Redis are healthy before relying on Kafka/APISIX).

### B3. Smoke-check infra

```bash
docker compose exec postgres pg_isready -U postgres -d ai4i_platform_db
docker compose exec -e REDISCLI_AUTH=changeme redis redis-cli ping
docker compose exec kafka /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092 >/dev/null && echo kafka:ok
curl -s -o /dev/null -w "apisix:%{http_code}\n" http://localhost:9080/
curl -s -o /dev/null -w "etcd:%{http_code}\n" http://localhost:2379/health
```

Expected: Postgres ready; Redis `PONG`; `kafka:ok`; APISIX/etcd reachable (non-connection-refused).

---

## Part C — Environment files & migrations

### C1. Generate per-service `.env` files

From `docker-compose/`:

```bash
cd "$AI4I_LOCAL/ai4i-core/docker-compose"
./scripts/setup-env.sh
```

The script:

1. Uses the parent directory as the ai4i-core repo root  
2. Creates/updates the repo-root `.env`  
3. Syncs Postgres/Redis/Kafka/branding from **docker-compose/.env** into the root `.env`  
4. Generates per-service `.env` under auth, platform-core, inference, Simple UI, Alembic, etc.

Host apps use `localhost` for Postgres/Redis (the script sets that).

### C2. Install migration dependencies

```bash
cd "$AI4I_LOCAL/ai4i-core"
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # must be 3.11.x+
cd infrastructure/databases
python -m pip install -r requirements.txt
cd ../..
```

### C3. Run migrations

```bash
cd "$AI4I_LOCAL/ai4i-core"
source .venv/bin/activate
./scripts/migrate.sh all upgrade
```

Expected: upgrades for `ai4iplatform_auth`, `ai4i_platform_db`, and `ai4iplatform_core`.

**Default admin (seeded):**

| Field | Value |
|-------|-------|
| Email | `admin@ai4inclusion.org` |
| Password | `ADMIN_PASSWORD` (literal string) |

> Keep the repo-root `.venv` for migrations only. Part D uses a **separate** `.venv` inside each `services/*` directory.

---

## Part D — Application services (one by one)

Open **three separate terminals**. Start services in this order.

> Use **`python3.11 -m venv`** for every service. If a `.venv` was created with Python 3.10, remove it (`rm -rf .venv`) and recreate.

### D1. Auth service — Terminal 1 (`:8081`)

```bash
cd "$AI4I_LOCAL/ai4i-core/services/auth-service"
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # must be 3.11.x+
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

**Expected:** `Application startup complete`  
**Verify:** http://localhost:8081/docs

### D2. Platform core — Terminal 2 (`:8095`)

```bash
cd "$AI4I_LOCAL/ai4i-core/services/platform-core-service"
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # must be 3.11.x+
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload
```

**Expected:** `Application startup complete`  
**Verify:** http://localhost:8095/docs

### D3. Inference — Terminal 3 (`:8090`)

```bash
cd "$AI4I_LOCAL/ai4i-core/services/inference-service"
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # must be 3.11.x+
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

**Expected:** `Application startup complete`  
**Verify:** http://localhost:8090/docs

**Harmless on app-minimal infra:**

- Kafka connection warnings if Kafka was not started — tracing/consumers may be limited; basic APIs still work.
- Missing `ffmpeg` — only affects some ASR/TTS paths.

### D4. Model endpoints

- **NMT (recommended local E2E model):** build/run in [Part A](#part-a--local-nmt-triton), then wire in [Part H](#part-h--wire-nmt-to-the-platform).
- **LLM / chat completions:** needs a separate OpenAI-compatible server (e.g. vLLM). Not covered by the NMT path; without it, UI `/api/v1/chat/completions` will fail even when the platform is healthy.

---

## Part E — Verify the stack

### E1. Health

```bash
curl -s http://localhost:8081/docs -o /dev/null -w "auth %{http_code}\n"
curl -s http://localhost:8095/docs -o /dev/null -w "platform-core %{http_code}\n"
curl -s http://localhost:8090/health
```

Expected inference health: `{"status":"healthy"}` (or equivalent healthy payload).

### E2. Login (Bearer token)

```bash
LOGIN=$(curl -s -X POST http://localhost:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}')

export TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "token length: ${#TOKEN}"
```

### E3. Platform-only check is enough here

Login + health prove Compose + apps. For a **real translation** through inference/UI, complete [Part A](#part-a--local-nmt-triton) (NMT up) and [Part H](#part-h--wire-nmt-to-the-platform).

---

## Part F — Frontend (optional)

```bash
cd "$AI4I_LOCAL/ai4i-core/frontend/simple-ui"
grep -E '^(API_URL|AUTH_SERVICE_URL)=' .env
# Expected:
#   API_URL=http://localhost:3000
#   AUTH_SERVICE_URL=http://localhost:8081

npm install
npm run dev
```

Open http://localhost:3000 — sign in with `admin@ai4inclusion.org` / `ADMIN_PASSWORD` (literal string).

Browser calls stay on `:3000`; the Next.js proxy performs forward-auth and forwards to auth `:8081`, platform-core `:8095`, and inference `:8090`. You do **not** need APISIX for this local UI path.

---

## Part G — Optional add-ons (monitoring / logging) — do these last

Only after core infra, migrations, and apps are verified:

```bash
cd "$AI4I_LOCAL/ai4i-core/docker-compose"

# Metrics / dashboards
docker compose --profile monitoring up -d

# Logs / traces → OpenSearch (needs Kafka from core)
# Requires: sudo sysctl -w vm.max_map_count=262144
docker compose --profile logging up -d
```

| UI | URL |
|----|-----|
| Grafana | http://localhost:3001 (default `admin` / `admin`) |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9095 |
| OpenSearch Dashboards | http://localhost:5601 |

---

## Part H — Wire NMT to the platform

Prerequisites: [Part A](#part-a--local-nmt-triton) NMT healthy on `:8000`, and Parts B–E complete (platform-core + inference up).

### H1. Point platform-core at NMT

If you set `TRITON_ENDPOINT_NMT=http://localhost:8000` in the **repo root** `.env` **before** migrations, the seed may already have the endpoint. Otherwise patch after platform-core is up.

> Platform-core’s SSRF guard often **rejects `localhost` / loopback**. Prefer a routable LAN IP (or host DNS) that reaches this machine’s `:8000`.

```bash
# List services and find NMT serviceId (seeded id below is usual)
curl -s "http://localhost:8095/api/v1/services" | python3.11 -m json.tool | less

# Example patch (replace HOST with a non-loopback address the probe can reach)
curl -s -X PATCH http://localhost:8095/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "services": [
      {
        "serviceId": "de9a4570f8c14f6859cb79c1934a4db9",
        "endpoint": "http://HOST:8000"
      }
    ]
  }'
```

### H2. NMT via inference (and UI)

```bash
TOKEN=$(curl -s -X POST http://localhost:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}' \
  | python3.11 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s -X POST http://localhost:8090/api/v1/nmt/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "input": [{"source": "Hello, how are you?"}],
    "config": {
      "serviceId": "de9a4570f8c14f6859cb79c1934a4db9",
      "language": {"sourceLanguage": "en", "targetLanguage": "hi"}
    }
  }'
```

Or in the UI: open **NMT** (not LLM) after sign-in.

---

## Port reference

### Applications (native)

| Service | URL | Process |
|---------|-----|---------|
| Auth | http://localhost:8081/docs | uvicorn |
| Platform core | http://localhost:8095/docs | uvicorn |
| Inference | http://localhost:8090/docs | uvicorn |
| Simple UI | http://localhost:3000 | Next.js |

### Compose core

| Service | Host port |
|---------|-----------|
| PostgreSQL | 5432 |
| Redis | 6379 |
| Kafka | 9092 |
| etcd | 2379 |
| APISIX HTTP / HTTPS / Admin / metrics | 9080 / 9443 / 9180 / 9091 |

### Optional profiles & models

| Service | Host port |
|---------|-----------|
| Prometheus / Alertmanager / Grafana | 9090 / 9095 / 3001 |
| node-exporter / kafka-exporter | 9100 / 9308 |
| OpenSearch / Dashboards | 9200 / 5601 |
| NMT Triton (external) | 8000 |

---

## Stopping and restarting

### Stop application services

`Ctrl+C` in each uvicorn / `npm run dev` terminal.

### Stop Compose (keep data)

```bash
cd "$AI4I_LOCAL/ai4i-core/docker-compose"
docker compose --profile monitoring --profile logging down
```

### Wipe Compose volumes (fresh DBs)

```bash
cd "$AI4I_LOCAL/ai4i-core/docker-compose"
docker compose --profile monitoring --profile logging down -v
# Re-run Part B → Part C (migrations re-seed)
```

### Full restart (keep data)

```bash
cd "$AI4I_LOCAL/ai4i-core/docker-compose"
docker compose up -d postgres redis   # or: docker compose up -d
# Re-run Part D terminals (auth → platform-core → inference)
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `setup-env.sh` cannot find ai4i-core | Run from `ai4i-core/docker-compose/` (parent must be the repo root) |
| Postgres connection refused from apps | Compose up? `POSTGRES_HOST=localhost` in service `.env`? Port `5432` free? |
| Redis `NOAUTH` / auth errors | `REDIS_PASSWORD` in compose `.env` must match service `.env` (re-run `setup-env.sh`) |
| Port already allocated | Change host ports in this pack’s `.env` or stop the conflicting process |
| OpenSearch fails to start | `sudo sysctl -w vm.max_map_count=262144` |
| Kafka warnings on inference | Start full core (`docker compose up -d`) or ignore for NMT-only paths |
| Login fails | Auth up on `:8081`? Migrations applied? Password is literal `ADMIN_PASSWORD` |
| UI API 502 / auth errors | Start backends **before** UI; confirm proxy targets `:8081` / `:8095` / `:8090` |
| `No matching distribution found for ai4i-core` | Venv is Python **&lt; 3.11** (often system `python3` = 3.10). Recreate with `rm -rf .venv && python3.11 -m venv .venv` |
| `python3.11: command not found` | Install Python 3.11+ from [python.org](https://www.python.org/downloads/) or your distro, then re-run Part C/D |
| Kafka `ECONNREFUSED` on `localhost:9093` | This compose maps Kafka to **9092**. Set `KAFKA_SERVER=localhost:9092` in service `.env` files (or re-run `./scripts/setup-env.sh`) and restart uvicorn |
| Prometheus / Alertmanager reload failed | Expected until you start `--profile monitoring` (Part G). Ignore for core verify |
| Redis `HELLO must be called…` warning | Soft redis-py / Redis 8 protocol warning; OK if catalogue warm / startup complete |
| `/api/v1/chat/completions` fails | Needs an **LLM** upstream — not Part A/H NMT. Host vLLM (or similar) or use **NMT** for simple local E2E |
| NMT 502 / endpoint rejected | Triton up on `:8000`? PATCH endpoint with a **non-loopback** host if SSRF blocks `localhost` |

---

## Related files in this pack

| File | Role |
|------|------|
| [README.md](README.md) | Quick reference (tiers, images, ports) |
| [MINIMAL-INFRA-REQUIREMENTS.md](MINIMAL-INFRA-REQUIREMENTS.md) | Host CPU / RAM / disk by compose mode |
| [docker-compose.yml](docker-compose.yml) | Service definitions |
| [.env.example](.env.example) | Infra + sync defaults |
| [scripts/setup-env.sh](scripts/setup-env.sh) | Generate ai4i-core service `.env` files |
