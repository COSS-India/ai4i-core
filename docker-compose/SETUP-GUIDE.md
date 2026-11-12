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
11. [Part H — Verify NMT via inference](#part-h--verify-nmt-via-inference)
12. [Port reference](#port-reference)
13. [Stopping and restarting](#stopping-and-restarting)
14. [Troubleshooting](#troubleshooting)
15. [Cleanup and fresh setup scripts](#cleanup-and-fresh-setup-scripts)

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

Same sequence as a from-scratch install (Compose → env/migrate → apps → NMT → verify). Part A (NMT) may also be done **before** Part B if you want Triton ready early; either works as long as `TRITON_ENDPOINT_NMT` is set **before** migrations.

```
0. (if re-installing) →  cleanup-local.sh   OR stop apps + Compose down -v   (clean slate)
1. Docker Compose     →  postgres + redis                         (wait healthy)
2. Docker Compose     →  kafka (+ kafka-init) + etcd + apisix     (wait healthy)
3. setup-env.sh       →  per-service .env files
4. repo-root .env     →  TRITON_ENDPOINT_NMT=http://127.0.0.1:8000   (before migrate)
5. migrate.sh         →  auth → platform_db → core (upgrade heads)
6. Terminal 1         →  auth-service      :8081
7. Terminal 2         →  platform-core     :8095
8. Terminal 3         →  inference         :8090   (first pip may take several minutes)
9. Part A             →  NMT Triton        :8000   (build/run; direct curl)  — or earlier
10. Part E / H        →  health → login → NMT via inference
11. (optional)        →  Simple UI         :3000
12. (optional LAST)   →  --profile monitoring and/or --profile logging
```

Do **not** start inference before auth/platform-core are up if you rely on shared secrets / catalogue data; follow Parts C → D in order. Set `TRITON_ENDPOINT_NMT` in the repo-root `.env` **before** Part C migrations (see [C1b](#c1b-set-nmt-triton-endpoint-before-migrations-required-for-nmt-e2e)).

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

This is the **simple model to host locally** for an end-to-end inference test. It is **CPU NMT (IndicTrans2 on Triton)** — not LLM/chat. You can skip Part A if you only need Compose + apps without a model.

For a real translation E2E: set `TRITON_ENDPOINT_NMT` **before** migrations ([C1b](#c1b-set-nmt-triton-endpoint-before-migrations-required-for-nmt-e2e)), build/run Triton here (before Compose, during apps, or after Part D — same commands), then verify with [Part H](#part-h--verify-nmt-via-inference).

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
# Recreate if a previous container exists
docker rm -f indictrans 2>/dev/null || true

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

curl -s -o /dev/null -w "triton:%{http_code}\n" http://127.0.0.1:8000/v2/health/ready
# Expected: triton:200
```

CUDA/GPU warnings at startup are **normal on CPU-only machines**.

### A5. Test direct translation

```bash
curl -s -X POST http://127.0.0.1:8000/v2/models/nmt/infer \
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

If you already have `ai4i-*` / `indictrans` containers or listeners on `8081` / `8095` / `8090` / `8000`, stop and wipe first ([Stopping and restarting](#stopping-and-restarting) or `cleanup-local.sh`) — then continue here.

**Step 1 — Postgres + Redis:**

```bash
docker compose up -d postgres redis

# Wait until both are healthy (do not continue early)
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-postgres 2>/dev/null)" = healthy ] \
  && [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-redis 2>/dev/null)" = healthy ]; do
  sleep 2
done
docker compose ps
```

Expected: `ai4i-postgres` and `ai4i-redis` are **Up (healthy)**.

Init creates databases `ai4iplatform_auth` and `ai4iplatform_core` on first Postgres boot.

**Step 2 — Kafka + etcd + APISIX** (required before setup-env / apps for the full platform flow):

```bash
docker compose up -d kafka kafka-init etcd apisix

until [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-kafka 2>/dev/null)" = healthy ] \
  && [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-etcd 2>/dev/null)" = healthy ] \
  && [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-apisix 2>/dev/null)" = healthy ]; do
  sleep 3
done
docker compose ps -a
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

### C1b. Set NMT Triton endpoint **before** migrations (required for NMT E2E)

The seed migration reads **`TRITON_ENDPOINT_NMT`** from the **ai4i-core repo-root** `.env` and writes it onto the seeded NMT service. **Do this before Part C3.** Do **not** rely on a later API PATCH (platform-core’s SSRF probe often blocks `localhost` / private IPs).

```bash
# Edit ai4i-core/.env (repo root — NOT docker-compose/.env)
# Host apps call Triton on the same machine, so loopback is fine for local native setup:
TRITON_ENDPOINT_NMT=http://127.0.0.1:8000
```

If Triton is only reachable on another host/IP that inference can call, use that instead:

```bash
TRITON_ENDPOINT_NMT=http://YOUR_REACHABLE_HOST:8000
```

Confirm before migrating:

```bash
grep '^TRITON_ENDPOINT_NMT=' "$AI4I_LOCAL/ai4i-core/.env"
```

> If you already migrated with a blank endpoint, wipe DBs (`docker compose down -v` + re-run Part B → C with the variable set) or ask the platform team how they prefer to re-seed. **This guide does not use PATCH `/api/v1/services` to set the NMT URL.**

### C2. Install migration dependencies

```bash
cd "$AI4I_LOCAL/ai4i-core"
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # must be 3.11.x+
python -m pip install -U pip
python -m pip install -r infrastructure/databases/requirements.txt
```

### C3. Run migrations

Run databases **one by one**. Auth and platform_db use a single Alembic head; **core currently has two heads**, so use `upgrade heads` for core (not `upgrade` / `all upgrade`, which target a single `head` and fail).

```bash
cd "$AI4I_LOCAL/ai4i-core"
source .venv/bin/activate

./scripts/migrate.sh ai4iplatform_auth upgrade
./scripts/migrate.sh ai4i_platform_db upgrade
./scripts/migrate.sh ai4iplatform_core upgrade heads

deactivate
```

Expected: each command finishes without error; NMT service seed includes the `TRITON_ENDPOINT_NMT` value from C1b.

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
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # must be 3.11.x+
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

**Expected:** `Application startup complete`  
**Verify:** `curl -s -o /dev/null -w "auth:%{http_code}\n" http://127.0.0.1:8081/docs` → `auth:200`

### D2. Platform core — Terminal 2 (`:8095`)

```bash
cd "$AI4I_LOCAL/ai4i-core/services/platform-core-service"
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # must be 3.11.x+
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload
```

**Expected:** `Application startup complete`  
**Verify:** `curl -s -o /dev/null -w "core:%{http_code}\n" http://127.0.0.1:8095/docs` → `core:200`

### D3. Inference — Terminal 3 (`:8090`)

```bash
cd "$AI4I_LOCAL/ai4i-core/services/inference-service"
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # must be 3.11.x+
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

> **First-time setup — wait for dependency download**  
> The first `pip install -r requirements.txt` for inference is **slow**. It pulls spaCy’s
> `en_core_web_lg` wheel (~**588 MB** from GitHub). You may see `ConnectionResetError` /
> `Retrying` and a long `Downloading en_core_web_lg-…whl` line with little progress — that is
> normal. **Do not interrupt**; leave the terminal until pip finishes and uvicorn prints
> `Application startup complete`. Later installs reuse the venv/cache and are much faster.  
> Until then, `http://localhost:8090/health` will fail / return connection refused — auth and
> platform-core can already be up while inference is still installing.

**Expected:** `Application startup complete`  
**Verify:** `curl -s http://127.0.0.1:8090/health` → healthy JSON / HTTP 200

**Harmless on app-minimal infra:**

- Kafka connection warnings if Kafka was not started — tracing/consumers may be limited; basic APIs still work.
- Missing `ffmpeg` — only affects some ASR/TTS paths.
- Prometheus / Alertmanager reload errors from platform-core — expected until `--profile monitoring`.

### D4. Model endpoints

- **NMT (recommended local E2E model):** build/run in [Part A](#part-a--local-nmt-triton), set `TRITON_ENDPOINT_NMT` before migrations ([C1b](#c1b-set-nmt-triton-endpoint-before-migrations-required-for-nmt-e2e)), then verify in [Part H](#part-h--verify-nmt-via-inference).
- **LLM / chat completions:** needs a separate OpenAI-compatible server (e.g. vLLM). Not covered by the NMT path; without it, UI `/api/v1/chat/completions` will fail even when the platform is healthy.

---

## Part E — Verify the stack

Run these **one by one** when each layer is ready (same checks as a completed from-scratch install).

### E1. Auth / platform-core / inference

```bash
curl -s -o /dev/null -w "auth:%{http_code}\n" http://127.0.0.1:8081/docs
# Expect: auth:200

curl -s -o /dev/null -w "core:%{http_code}\n" http://127.0.0.1:8095/docs
# Expect: core:200

curl -s http://127.0.0.1:8090/health
# Expect: healthy JSON / HTTP 200
```

### E2. Login (Bearer token)

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}' \
  | python3.11 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
echo "token length: ${#TOKEN}"
```

### E3. Platform-only check is enough here

Login + health prove Compose + apps. For a **real translation** through inference/UI, complete [Part A](#part-a--local-nmt-triton) (NMT up), ensure `TRITON_ENDPOINT_NMT` was set before migrations, and run [Part H](#part-h--verify-nmt-via-inference).

---

## Part F — Frontend (optional)

```bash
cd "$AI4I_LOCAL/ai4i-core/frontend/simple-ui"
grep -E '^(API_URL|AUTH_SERVICE_URL|ENABLED_TASK_TYPES)=' .env
# Expected:
#   API_URL=http://localhost:3000
#   AUTH_SERVICE_URL=http://localhost:8081
#   ENABLED_TASK_TYPES=…   (see below)
```

### F1. Enable NMT in the UI (required for local translation E2E)

The home/catalog cards are gated by **`ENABLED_TASK_TYPES`** in `frontend/simple-ui/.env` (runtime; no rebuild). `./scripts/setup-env.sh` generates this from `frontend/simple-ui/env.template`.

Local template default (after Part C `setup-env`):

```bash
ENABLED_TASK_TYPES=llm,nmt
```

| Value | UI shows |
|-------|----------|
| `llm` | LLM card only |
| `llm,nmt` (local template default) | LLM + NMT |
| unset / empty | Full catalog (all task types) |

If your `.env` still has `llm` only (older generate), set `llm,nmt` and restart `npm run dev`. Backend NMT still works via curl ([Part H](#part-h--verify-nmt-via-inference)) even if the UI only lists LLM.

### F2. Start Simple UI

```bash
cd "$AI4I_LOCAL/ai4i-core/frontend/simple-ui"
npm install
npm run dev
```

Open http://localhost:3000 — sign in with `admin@ai4inclusion.org` / `ADMIN_PASSWORD` (literal string). Open the **NMT** card (not LLM) for translation.

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

## Part H — Verify NMT via inference

Prerequisites:

- [Part A](#part-a--local-nmt-triton) — Triton NMT healthy on `:8000`
- [C1b](#c1b-set-nmt-triton-endpoint-before-migrations-required-for-nmt-e2e) — `TRITON_ENDPOINT_NMT` set in **repo-root** `.env` **before** migrations
- Parts B–E — Compose, migrate, apps up

**Do not PATCH** `/api/v1/services` to set the NMT URL. The catalogue endpoint is seeded from `TRITON_ENDPOINT_NMT` at migration time. A later PATCH is blocked by platform-core SSRF checks for typical local hosts (`127.0.0.1`, private LAN IPs).

### H1. Confirm the seeded endpoint (optional)

```bash
curl -s "http://127.0.0.1:8095/api/v1/services" | python3.11 -c '
import sys, json
data = json.load(sys.stdin)
# response shape may be a list or {"services": [...]}
items = data if isinstance(data, list) else data.get("services") or data.get("data") or []
for s in items:
    sid = s.get("serviceId") or s.get("service_id") or ""
    name = s.get("name") or ""
    if "nmt" in name.lower() or sid == "de9a4570f8c14f6859cb79c1934a4db9":
        print(name, sid, s.get("endpoint"))
'
```

Expect a non-empty `endpoint` such as `http://127.0.0.1:8000`.

### H2. NMT via inference (and UI)

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}' \
  | python3.11 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s -X POST http://127.0.0.1:8090/api/v1/nmt/inference \
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

Expect Hindi in `output[].target` (e.g. `नमस्ते, आप कैसे हैं?`). Or in the UI: set `ENABLED_TASK_TYPES=llm,nmt` ([Part F](#part-f--frontend-optional)), restart Simple UI, then open **NMT** (not LLM) after sign-in.

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
| NMT 502 / blank endpoint | Triton up on `:8000`? Was `TRITON_ENDPOINT_NMT` set in **repo-root** `.env` **before** migrate ([C1b](#c1b-set-nmt-triton-endpoint-before-migrations-required-for-nmt-e2e))? Re-migrate from a wiped DB if it was blank. Do not PATCH locally (SSRF). |
| Inference never becomes healthy on first setup | Still downloading `en_core_web_lg` (~588 MB). Wait for `pip install` to finish (see [Part D3](#d3-inference--terminal-3-8090)); check the inference terminal (or `.local-run-logs/inference.log` if you used `setup-local.sh`) |
| Alembic `Multiple heads are present` / `Can't locate revision` on core | Use `./scripts/migrate.sh ai4iplatform_core upgrade heads` (see [C3](#c3-run-migrations)). Do not use `all upgrade` until the platform team lands a merge revision. |

---

## Cleanup and fresh setup scripts

Parts A–H above are the canonical from-scratch path. The helpers below automate the same
sequence (Compose → `setup-env` → `TRITON_ENDPOINT_NMT` → migrate with `upgrade heads` →
apps → NMT). Cleanup and setup are **separate** — cleanup does not start anything; setup
refuses to run if a local stack is already present.

### 1) Cleanup — remove all local resources

Stops host apps, removes the NMT container, and runs Compose `down -v` (containers **and** volumes). Nothing remains to auto-start on reboot.

```bash
export AI4I_LOCAL=/path/to/cloned-repos
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/cleanup-local.sh"
```

Optional: also delete the HuggingFace model cache volume (`REMOVE_HF_CACHE=1`).

### 2) Fresh setup — rebuild from scratch

Brings up the same layers as Parts B–D + A. If a previous local stack is still running
(`ai4i-*` / `indictrans`, or ports `8081`/`8095`/`8090`/`8000`), **setup exits** and prints
that you must run `cleanup-local.sh` first — it does not clean up automatically.

After resources start, the script prints the Part E / A4–A5 / H verify curls to run
manually when each layer is ready (it does not wait or E2E-test for you):

```bash
export AI4I_LOCAL=/path/to/cloned-repos
export HF_TOKEN=hf_...   # HuggingFace Read token (IndicTrans2 access)
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/setup-local.sh"
```

Requires `model-hosting/nmt-triton` under `$AI4I_LOCAL` (or set `NMT_SRC=`).

On first run, inference may still be installing `en_core_web_lg` (~588 MB) after the script
exits — see [Part D3](#d3-inference--terminal-3-8090). Watch
`docker-compose/.local-run-logs/inference.log`, then run the printed curl steps (auth →
platform-core → inference health → Triton → direct NMT → inference NMT).

---

## Related files in this pack

| File | Role |
|------|------|
| [README.md](README.md) | Quick reference (tiers, images, ports) |
| [MINIMAL-INFRA-REQUIREMENTS.md](MINIMAL-INFRA-REQUIREMENTS.md) | Host CPU / RAM / disk by compose mode |
| [docker-compose.yml](docker-compose.yml) | Service definitions |
| [.env.example](.env.example) | Infra + sync defaults |
| [scripts/README.md](scripts/README.md) | Usage of all scripts in this folder |
| [scripts/setup-env.sh](scripts/setup-env.sh) | Generate ai4i-core service `.env` files |
| [scripts/cleanup-local.sh](scripts/cleanup-local.sh) | Tear down apps + Compose volumes + NMT |
| [scripts/setup-local.sh](scripts/setup-local.sh) | Fresh install; prints verify commands |
