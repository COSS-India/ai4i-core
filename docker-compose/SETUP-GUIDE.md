# Local setup guide — Docker Compose + AI4I-Orchestrate

Manual step-by-step setup on Linux. Same sequence as interactive [`scripts/setup-local.sh`](scripts/setup-local.sh) — use this guide when you want to run each step yourself.

| Layer | How it runs |
|-------|-------------|
| Infra | **Docker Compose** (this folder) |
| Auth / platform-core / inference | **Native uvicorn** (one terminal each) |
| Simple UI | **Native Next.js** (optional) |
| NMT | **Separate Docker** (`model-hosting/nmt-triton`) — optional, after apps |

**OS:** Linux (Ubuntu tested). **Sizing:** [MINIMAL-INFRA-REQUIREMENTS.md](MINIMAL-INFRA-REQUIREMENTS.md).

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture](#2-architecture)
3. [Workspace](#3-workspace)
4. [Choose a mode](#4-choose-a-mode)
5. [Step 1 — App-minimal Compose](#step-1--app-minimal-compose)
6. [Step 2 — Logging (optional)](#step-2--logging-optional)
7. [Step 3 — Tracing / Kafka (optional)](#step-3--tracing--kafka-optional)
8. [Step 4 — Monitoring (optional)](#step-4--monitoring-optional)
9. [Step 5 — Env + migrations](#step-5--env--migrations)
10. [Step 6 — Host apps](#step-6--host-apps)
11. [Step 7 — Verify base stack](#step-7--verify-base-stack)
12. [Step 8 — Simple UI (optional)](#step-8--simple-ui-optional)
13. [Step 9 — NMT Triton (optional)](#step-9--nmt-triton-optional)
14. [Step 10 — Verify NMT](#step-10--verify-nmt)
15. [Ports / stop / troubleshoot](#ports--stop--troubleshoot)
16. [Scripts](#scripts)

> **Local vs production:** this Docker local setup does **not** run APISIX, etcd, or a gateway profile. Host uvicorn apps and Simple UI talk to each other directly (`:8081` / `:8095` / `:8090`). In **production**, requests go through the **APISIX gateway** (cluster gateway); that resource is out of scope for this Compose pack.

---

## 1. Prerequisites

### Hardware (app-minimal: Postgres + Redis + host apps)

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 4 GB | 8 GB+ (16 GB+ if NMT / monitoring / logging + Kafka) |
| Disk | 10 GB free | 40 GB+ (NMT image alone is large) |
| CPU | 2 vCPU (x86_64) | Multi-core |
| GPU | Not required | — |

Full sizing by mode (incl. NMT add-on): [MINIMAL-INFRA-REQUIREMENTS.md](MINIMAL-INFRA-REQUIREMENTS.md).

### Software

| Tool | Required for |
|------|----------------|
| Docker Engine 24+ & Compose v2.20+ | Compose infra + optional NMT container |
| Git | Clone repos |
| **Python 3.11+** (`python3.11` / `python3.12` / `python3`) + pip | Migrations + host apps (`ai4i-core` needs `>=3.11`) |
| HuggingFace Read token | Step 9 only — gated IndicTrans2 |
| Node.js 18+ & npm | Step 8 only |

```bash
docker --version && docker compose version && docker ps
git --version
python3.11 --version || python3 --version   # must be 3.11+ (not 3.10)
# setup-local.sh auto-picks python3.11 → 3.12 → 3.13 → python3
# or: export PYTHON_BIN=python3.12
# node --version              # optional — Simple UI
```

On older Ubuntu hosts `python3` may still be **3.10** — use **`python3.11+`** for venvs (or set `PYTHON_BIN`).

#### HuggingFace (only if you run Step 9 NMT)

1. Account at [huggingface.co](https://huggingface.co)
2. Agree access on the IndicTrans2 model pages (en-indic, indic-en, indic-indic dist models)
3. Create a **Read** token at [settings/tokens](https://huggingface.co/settings/tokens) — never commit it

---

## 2. Architecture

Apps are **not** started by Docker Compose. Infra is Compose; backends/UI run on the host.

### 2.1 Runtime (request path)

```
┌──────────────────────────────────────────────────────────────────┐
│  UI LAYER  (native Next.js — optional, start last)               │
│  Simple UI  :3000                                                │
│    └─ /api/v1/* → Next.js proxy → forward-auth + backends        │
└───────────────────────────────┬──────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────┐
│  BACKEND SERVICES  (native uvicorn — one terminal each)          │
│  1) auth-service :8081                                           │
│  2) platform-core :8095                                          │
│  3) inference :8090                                              │
└───────────────┬───────────────────────────────┬──────────────────┘
                │                               │
                ▼                               ▼
┌───────────────────────────────┐   ┌──────────────────────────────┐
│  COMPOSE (local)              │   │  AI MODEL (optional)         │
│  PostgreSQL  :5432            │   │  indictrans (Triton) :8000   │
│  Redis       :6379            │   │  /v2/models/nmt/infer        │
│  Kafka       :9092 (optional) │   └──────────────────────────────┘
└───────────────────────────────┘
```

No APISIX/gateway in this local path — UI and curls hit uvicorn directly. Production uses APISIX as the gateway.

### 2.2 Compose infra layers

```
┌──────────────────────────────────────────────────────────────────┐
│  LOCAL COMPOSE                                                   │
│  1) postgres :5432   redis :6379     ← app-minimal (required)    │
│  2) kafka :9092                      ← optional tracing/logging  │
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

**Required locally:** Postgres, Redis.  
**Optional:** Kafka (tracing), `--profile monitoring`, `--profile logging`.  
**Not in this pack:** APISIX + etcd (no `gateway` profile). **Production** uses the APISIX gateway; local Docker setup does not include that resource.

### 2.3 Startup order

Same order as `setup-local.sh` / the steps below:

```
0. (re-install)     →  cleanup-local.sh  OR  stop apps + compose down -v
1. Compose          →  postgres + redis                         (app-minimal)
2. (optional)       →  --profile logging
3. (optional)       →  kafka + kafka-init                       (tracing)
4. (optional)       →  --profile monitoring
5. setup-env.sh     →  per-service .env files
6. repo-root .env   →  TRITON_ENDPOINT_NMT=http://127.0.0.1:8000  (before migrate)
7. migrate.sh       →  auth → platform_db → core (upgrade heads)
8. Terminals        →  auth :8081 → platform-core :8095 → inference :8090
9. Verify           →  docs / health / login
10. (optional)      →  Simple UI :3000
11. (optional)      →  NMT Triton :8000  (HF token only here)
12. (optional)      →  NMT verify curls / UI NMT card
```

Set `TRITON_ENDPOINT_NMT` **before** migrations if you will run NMT later (no API PATCH).

---

## 3. Workspace

```bash
export AI4I_LOCAL=~/ai4i-local-setup   # parent of ai4i-core/
mkdir -p "$AI4I_LOCAL" && cd "$AI4I_LOCAL"

git clone --branch <release-tag> git@github.com:COSS-India/ai4i-core.git
# For NMT later:
git clone -b feat/nmt-local-setup git@github.com:COSS-India/model-hosting.git
```

```
$AI4I_LOCAL/
├── ai4i-core/          # platform + docker-compose/
└── model-hosting/      # nmt-triton/ (Step 9)
```

If a previous stack is present (`ai4i-*`, `indictrans`, ports `8081`/`8095`/`8090`/`8000`), clean first:

```bash
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/cleanup-local.sh"
# or: stop uvicorn terminals + docker compose --profile monitoring --profile logging down -v
```

---

## 4. Choose a mode

Same options as `setup-local.sh` / [MINIMAL-INFRA-REQUIREMENTS](MINIMAL-INFRA-REQUIREMENTS.md) §2:

| Mode | Do these steps |
|------|----------------|
| **1 — App-minimal** | Steps 1 → 5 → 6 → 7 (then optional 8–10) |
| **2 — + monitoring** | 1 → 4 → 5 → 6 → 7 |
| **3 — + logging (optional tracing)** | 1 → 2 → (3 if tracing) → 5 → 6 → 7 |
| **4 — monitoring + logging** | 1 → 2 → (3) → 4 → 5 → 6 → 7 |

All compose commands below: `cd "$AI4I_LOCAL/ai4i-core/docker-compose"`.

---

## Step 1 — App-minimal Compose

Postgres + Redis — required for host apps.

```bash
cd "$AI4I_LOCAL/ai4i-core/docker-compose"
cp -n .env.example .env

docker compose up -d postgres redis
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-postgres 2>/dev/null)" = healthy ] \
  && [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-redis 2>/dev/null)" = healthy ]; do
  sleep 2
done
docker compose ps
```

---

## Step 2 — Logging (optional)

Modes 3–4.

```bash
sudo sysctl -w vm.max_map_count=262144
# Fluent Bit needs Kafka — start broker first, then logging services only
docker compose up -d kafka kafka-init
docker compose up -d opensearch opensearch-dashboards fluent-bit
# Do not use bare: docker compose --profile logging up -d
# (this pack has no APISIX/etcd/gateway — production uses APISIX; local setup does not)
```

---

## Step 3 — Tracing / Kafka (optional)

Only if you want optional tracing (after Step 2). Not required for app-minimal or NMT E2E.

```bash
docker compose up -d kafka kafka-init
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-kafka 2>/dev/null)" = healthy ]; do
  sleep 3
done
# kafka-init should exit 0
```

---

## Step 4 — Monitoring (optional)

Modes 2 and 4.

```bash
# alertmanager.yml + synced rule files are gitignored — seed once if missing:
test -f config/alertmanager/alertmanager.yml \
  || cp config/alertmanager/alertmanager.default.yml config/alertmanager/alertmanager.yml
mkdir -p config/prometheus/rules
for f in application-alerts.yml infrastructure-alerts.yml; do
  test -f "config/prometheus/rules/$f" || printf 'groups: []\n' > "config/prometheus/rules/$f"
done

docker compose up -d prometheus alertmanager grafana node-exporter kafka-exporter
# If a host port is busy, change the matching *_PORT in docker-compose/.env and re-run
# (AUTH_SERVICE_PORT, PLATFORM_CORE_PORT, INFERENCE_SERVICE_PORT, NODE_EXPORTER_PORT, …).
# Simple UI stays :3000; NMT stays :8000/:8002. Preflight prints the ENV KEY column.
# setup-local.sh checks required ports before starting and exits if any are occupied.
```

| UI | URL |
|----|-----|
| Grafana | http://localhost:3001 (`admin` / `admin`) |
| Prometheus | http://localhost:9090 |
| OpenSearch Dashboards | http://localhost:5601 |

---

## Step 5 — Env + migrations

```bash
cd "$AI4I_LOCAL/ai4i-core/docker-compose"
./scripts/setup-env.sh
```

Seed NMT URL in **repo-root** `.env` **before** migrate (needed if you will run Step 9; no API PATCH):

```bash
# ai4i-core/.env  (NOT docker-compose/.env)
TRITON_ENDPOINT_NMT=http://127.0.0.1:8000
grep '^TRITON_ENDPOINT_NMT=' "$AI4I_LOCAL/ai4i-core/.env"
```

```bash
cd "$AI4I_LOCAL/ai4i-core"
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r infrastructure/databases/requirements.txt

./scripts/migrate.sh ai4iplatform_auth upgrade
./scripts/migrate.sh ai4i_platform_db upgrade
./scripts/migrate.sh ai4iplatform_core upgrade heads   # dual heads — not "all upgrade"

deactivate
```

Seeded admin: `admin@ai4inclusion.org` / `ADMIN_PASSWORD`.

---

## Step 6 — Host apps

Three terminals. Use `python3.11` for every venv.

**Terminal 1 — auth `:8081`**

```bash
cd "$AI4I_LOCAL/ai4i-core/services/auth-service"
rm -rf .venv && python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -U pip && python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

**Terminal 2 — platform-core `:8095`**

```bash
cd "$AI4I_LOCAL/ai4i-core/services/platform-core-service"
rm -rf .venv && python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -U pip && python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload
```

**Terminal 3 — inference `:8090`**

```bash
cd "$AI4I_LOCAL/ai4i-core/services/inference-service"
rm -rf .venv && python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -U pip && python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

First inference `pip install` pulls `en_core_web_lg` (~588 MB) — wait for `Application startup complete`. Kafka warnings without Step 3 are normal.

---

## Step 7 — Verify base stack

```bash
curl -s -o /dev/null -w "auth:%{http_code}\n" http://127.0.0.1:8081/docs
curl -s -o /dev/null -w "core:%{http_code}\n" http://127.0.0.1:8095/docs
curl -s http://127.0.0.1:8090/health

TOKEN=$(curl -s -X POST http://127.0.0.1:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}' \
  | python3.11 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
echo "token length: ${#TOKEN}"
```

`setup-local.sh` re-runs a live status table **after** the Simple UI prompt (before NMT): backends always; UI if started. If you skip UI, it prints the login/health sample curls above.

---

## Step 8 — Simple UI (optional)

```bash
cd "$AI4I_LOCAL/ai4i-core/frontend/simple-ui"
grep -E '^(API_URL|ENABLED_TASK_TYPES)=' .env
# ENABLED_TASK_TYPES=llm,nmt   # needed for NMT card (from env.template via setup-env)

npm install && npm run dev
```

Open http://127.0.0.1:3000 — `admin@ai4inclusion.org` / `ADMIN_PASSWORD`. UI proxies directly to `:8081` / `:8095` / `:8090`.

---

## Step 9 — NMT Triton (optional)

Add-on sizing: [MINIMAL-INFRA-REQUIREMENTS §2.5](MINIMAL-INFRA-REQUIREMENTS.md#25-nmt-triton-only--add-on-to-21-24). Needs HF Read token + model access ([IndicTrans2 repos](https://huggingface.co/ai4bharat)).

```bash
cd "$AI4I_LOCAL/model-hosting/nmt-triton"
ls Dockerfile models/nmt/config.pbtxt models/nmt/1/model.py

docker build -t nmt-triton-cpu .

docker rm -f indictrans 2>/dev/null || true
docker run -d \
  -p 8000:8000 -p 8002:8002 \
  -v hf-cache:/cache \
  -e HF_TOKEN=hf_your_token_here \
  --name indictrans \
  nmt-triton-cpu
```

---

## Step 10 — Verify NMT

```bash
curl -s -o /dev/null -w "triton:%{http_code}\n" http://127.0.0.1:8000/v2/health/ready

curl -s -X POST http://127.0.0.1:8000/v2/models/nmt/infer \
  -H "Content-Type: application/json" \
  -d '{"inputs":[
    {"name":"INPUT_TEXT","shape":[1,1],"datatype":"BYTES","data":["Hello, how are you?"]},
    {"name":"INPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["en"]},
    {"name":"OUTPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["hi"]}]}'
# First call may download weights into hf-cache

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

Expect Hindi in `output[].target`. UI: open **NMT** card (not LLM).

---

## Ports / stop / troubleshoot

| What | Ports |
|------|-------|
| Apps (uvicorn ports override in `docker-compose/.env`) | `AUTH_SERVICE_PORT=8081` · `PLATFORM_CORE_PORT=8095` · `INFERENCE_SERVICE_PORT=8090` · UI fixed `3000` |
| App-minimal | `5432` · `6379` |
| Kafka (optional tracing) | `9092` |
| Monitoring | `9090` · `9095` · `3001` · `9100` · `9308` |
| Logging | `9200` · `5601` |
| NMT | `8000` · `8002` (fixed; `TRITON_ENDPOINT_NMT` in repo-root `.env`) |

```bash
# Stop apps: Ctrl+C in each terminal
cd "$AI4I_LOCAL/ai4i-core/docker-compose"
docker compose --profile monitoring --profile logging down      # keep volumes
docker compose --profile monitoring --profile logging down -v   # wipe DBs
```

| Symptom | Fix |
|---------|-----|
| `Multiple heads` on core migrate | `upgrade heads` (Step 5) — not `all upgrade` |
| Migrate hangs / `psql -h 127.0.0.1` times out but `docker exec … psql` works | `COMPOSE_SUBNET` overlaps VPN (often `172.31.0.0/16` via `tun0`). Set `COMPOSE_SUBNET=172.28.0.0/16`, recreate compose network (`down` then `up`) |
| NMT blank endpoint / 502 | `TRITON_ENDPOINT_NMT` in repo-root `.env` before migrate; wipe + re-migrate if blank. No PATCH |
| Inference slow first start | Waiting on `en_core_web_lg` (~588 MB) |
| Kafka warnings | Expected without Step 3 |
| Python package not found | Recreate venv with `python3.11` |
| OpenSearch fails | `vm.max_map_count=262144` |
| UI only shows LLM | `ENABLED_TASK_TYPES=llm,nmt` in `simple-ui/.env` |

---

## Scripts

Automate the same steps (interactive mode pick + confirmations; optional Simple UI; then optional NMT/`HF_TOKEN`):

```bash
export AI4I_LOCAL=/path/to/cloned-repos
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/cleanup-local.sh"   # wipe first if needed
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/setup-local.sh"
```

Details: [scripts/README.md](scripts/README.md).

| File | Role |
|------|------|
| [README.md](README.md) | Quick reference |
| [MINIMAL-INFRA-REQUIREMENTS.md](MINIMAL-INFRA-REQUIREMENTS.md) | Host sizing by mode |
| [docker-compose.yml](docker-compose.yml) | Services |
| [scripts/setup-env.sh](scripts/setup-env.sh) | Generate service `.env` files |
| [scripts/cleanup-local.sh](scripts/cleanup-local.sh) | Tear down |
| [scripts/setup-local.sh](scripts/setup-local.sh) | Interactive install |
