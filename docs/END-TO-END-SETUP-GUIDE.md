# End-to-End Local Setup Guide — AI4I-Orchestrate + NMT (CPU)

## About this guide

This guide documents how to run **AI4I-Orchestrate** and a local **NMT** model together on **Linux** — auth, inference APIs, optional web UI, and CPU-based translation via Triton. You do **not** need a GPU for the NMT path described here.

It lives in the **ai4i-core** repository at `docs/END-TO-END-SETUP-GUIDE.md`.

### Two repositories

| Repository | Role |
|------------|------|
| **[ai4i-core](https://github.com/COSS-India/ai4i-core)** | Platform services, migrations, docker-compose, Simple UI, and this guide |
| **[model-hosting](https://github.com/COSS-India/model-hosting)** (`feat/nmt-local-setup`) | Local model hosting — **`nmt-triton/`** for IndicTrans2 on Triton ([Part A](#part-a--local-nmt-triton)) |

### What you will set up

| Component | Location | What it does |
|-----------|----------|----------------|
| **NMT (Triton)** | `model-hosting/nmt-triton/` | IndicTrans2 in Docker for English ↔ Indic translation |
| **AI4I-Orchestrate** | `ai4i-core/` | auth, platform-core, inference, Postgres, Redis, Simple UI |

When setup is complete, you can send *“Hello, how are you?”* through the platform API and receive a Hindi translation — entirely on `localhost`.

### How it runs locally

- **Docker** — PostgreSQL, Redis, and the NMT Triton container
- **Native Python (uvicorn)** — auth, platform-core, and inference on the Linux host

> **OS support:** This setup is **Linux only** (Ubuntu tested).

Start with [§1 System prerequisites](#1-system-prerequisites), then work through the parts in order.

---

## Table of contents

1. [System prerequisites](#1-system-prerequisites)
2. [Architecture](#2-architecture)
3. [Clone repositories](#3-clone-repositories)
4. [Part A — Local NMT (Triton)](#part-a--local-nmt-triton)
5. [Part B — AI4I-Orchestrate platform](#part-b--ai4i-orchestrate-platform)
6. [Part C — Application services](#part-c--application-services)
7. [Part D — Verify end-to-end NMT](#part-d--verify-end-to-end-nmt)
8. [Part E — Frontend (optional)](#part-e--frontend-optional)
9. [Port reference](#port-reference)
10. [Stopping and restarting](#stopping-and-restarting)
11. [Troubleshooting](#troubleshooting)
12. [Other model services](#other-model-services)
13. [Tracing and observability](#tracing-and-observability)

---

## 1. System prerequisites

### Hardware

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 8 GB | 16 GB+ (NMT model load uses several GB) |
| Disk | 40 GB free | 50 GB+ (Triton image ~18 GB + models + ai4i-core) |
| CPU | x86_64 with AVX2 | Multi-core (translation is CPU-bound) |
| GPU | **Not required** | — |

### Operating system

- **Linux only** (Ubuntu tested)

### Software to install

Install each tool from its **official documentation** for Linux. This guide does **not** include distro-specific install commands — follow the vendor docs, then run the verification commands below.

| Tool | Required for | Official install documentation |
|------|--------------|-------------------------------|
| Docker & Docker Compose | Parts A–E | [Docker Engine](https://docs.docker.com/get-started/get-docker/) · [Compose](https://docs.docker.com/compose/install/) |
| Git | §3 clone | [git-scm.com/downloads](https://git-scm.com/downloads) |
| Python **>= 3.11** | Parts B–C | [python.org/downloads](https://www.python.org/downloads/) |
| pip | Part B migrations | [pip installation](https://pip.pypa.io/en/stable/installation/) |
| Node.js **18+** & npm | Part E (frontend) | [nodejs.org/en/download](https://nodejs.org/en/download) |
| PostgreSQL client (`psql`) | Optional verification | [postgresql.org/download](https://www.postgresql.org/download/) |

#### Verify installations

```bash
docker --version          # e.g. Docker 24+
docker compose version    # e.g. Compose v2.20+
docker ps                 # must not error
git --version
python3 --version              # must be 3.11.x or newer (e.g. 3.12)
python3 -m pip --version       # pip must be available for that interpreter
node --version                 # v18+ (skip if not running the frontend)
npm --version
```

#### Python commands in this guide

AI4I-Orchestrate requires **Python >= 3.11** (`ai4i-core` declares `requires-python >= 3.11`).

Throughout this guide, **`python3`** means the Python 3.11+ executable on your machine (on many systems that is literally the `python3` command; on others it may be `python3.12`, etc.). Before continuing, confirm:

```bash
python3 --version   # must print 3.11 or newer
```

If `python3` is too old or missing, install Python >= 3.11 from the [official downloads](https://www.python.org/downloads/) and use whatever executable that install provides in place of `python3` in the steps below.

All Python usage in Parts B–E follows the same pattern:

| Step | Command |
|------|---------|
| Create a virtualenv | `python3 -m venv .venv` |
| Activate it | `source .venv/bin/activate` |
| Install packages | `python3 -m pip install ...` |
| Run a service | `python3 -m uvicorn ...` |
| One-off scripts (Parts D–E) | `python3 -c "..."` |

After `source .venv/bin/activate`, `python3` and `python3 -m pip` use the virtualenv automatically.

If `python3 -m pip` fails, install pip for that interpreter per the [official pip documentation](https://pip.pypa.io/en/stable/installation/).

#### HuggingFace account & token (required for NMT)

IndicTrans2 model weights are **gated**. Before building NMT:

1. Create an account at [huggingface.co](https://huggingface.co)
2. Open each model page and click **“Agree and access repository”**:
   - [indictrans2-en-indic-dist-200M](https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M)
   - [indictrans2-indic-en-dist-200M](https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M)
   - [indictrans2-indic-indic-dist-320M](https://huggingface.co/ai4bharat/indictrans2-indic-indic-dist-320M)
3. Create a **Read** token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (`hf_...`). **Keep it secret** — never commit it.

   When creating the token, you will be asked to choose a **Token type**:

   | Option | Select? |
   |--------|---------|
   | Fine-grained | No |
   | **Read** | **Yes — choose this** |
   | Write | No |

   > **Note:** The token type **cannot be changed after token creation.** Make sure **Read** is selected before confirming.

### Pre-flight checklist

Run this once; every line should succeed:

```bash
docker ps
python3 --version          # must be 3.11.x or newer
python3 -m pip --version
git --version
node --version       # optional unless running the frontend
```

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  UI LAYER  (native Next.js dev server)                           │
│  Simple UI  :3000                                                │
│    └─ /api/v1/* → src/pages/api/v1/[...proxy].ts                 │
│         path routing + forward-auth (/api/v1/auth/validate)      │
│         injects X-User-ID / X-Tenant-ID / X-Permission-IDs       │
└───────────────────────────────┬──────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────┐
│  BACKEND SERVICES  (native uvicorn on Linux host)                │
│  auth-service :8081  │  platform-core :8095  │  inference :8090  │
└───────────────┬───────────────────────────────┬──────────────────┘
                │                               │
                ▼                               ▼
┌───────────────────────────────┐   ┌──────────────────────────────┐
│  SYSTEM / RECORDS  (Docker)   │   │  AI MODEL LAYER  (Docker)    │
│  PostgreSQL  :5432            │   │  indictrans (Triton)  :8000  │
│  Redis       :6379            │   │  /v2/models/nmt/infer        │
└───────────────────────────────┘   └──────────────────────────────┘
```

---

## 3. Clone repositories

Create a workspace and clone **both repositories**:

```bash
mkdir -p ~/ai4i-local-setup
cd ~/ai4i-local-setup

# Platform — clone the release tag your team uses (not master/main)
# See: https://github.com/COSS-India/ai4i-core/releases
git clone --branch <release-tag> git@github.com:COSS-India/ai4i-core.git

# Local NMT model hosting (nmt-triton/) — branch with CPU NMT assets
git clone -b feat/nmt-local-setup git@github.com:COSS-India/model-hosting.git
```

Replace `<release-tag>` with the tag from the [ai4i-core releases page](https://github.com/COSS-India/ai4i-core/releases) (for example `release-2.2`). Use the tag that matches your project or internal documentation.

| Repository | Ref | Purpose |
|------------|-----|---------|
| `ai4i-core` | **release tag** from [releases](https://github.com/COSS-India/ai4i-core/releases) | Platform services, migrations, UI |
| `model-hosting` | branch `feat/nmt-local-setup` | `nmt-triton/` (CPU IndicTrans2) and `setup-docs/` for other models |

Verify after cloning:

```bash
cd ~/ai4i-local-setup/ai4i-core && git describe --tags                    # your release tag
cd ~/ai4i-local-setup/model-hosting && git branch --show-current          # feat/nmt-local-setup
ls ~/ai4i-local-setup/model-hosting/nmt-triton/Dockerfile                 # NMT project present
```

**Set `AI4I_LOCAL` now** — every Part below uses this variable. Run it in each new terminal (or add to `~/.bashrc`):

```bash
export AI4I_LOCAL=~/ai4i-local-setup   # adjust if you used a different directory
echo "$AI4I_LOCAL"                     # must print your workspace path, not a blank line
```

Final layout:

```
~/ai4i-local-setup/
├── ai4i-core/
│   ├── docker-compose-local.yml
│   ├── env.template
│   ├── docs/
│   │   └── END-TO-END-SETUP-GUIDE.md   ← this guide
│   └── services/
└── model-hosting/
    └── nmt-triton/                     ← Part A — local NMT (Triton + IndicTrans2)
```

---

## Part A — Local NMT (Triton)

NMT lives in the **model-hosting** repository under `nmt-triton/`.

### A1. Verify NMT project files

```bash
cd "$AI4I_LOCAL/model-hosting/nmt-triton"
ls -la Dockerfile models/nmt/config.pbtxt models/nmt/1/model.py
```

**Expected:**

```
Dockerfile
models/nmt/config.pbtxt
models/nmt/1/model.py
```

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
```

Wait until logs show:

```
Started HTTPService at 0.0.0.0:8000
```

Health check:

```bash
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

**Expected (example):**

```json
{
  "model_name": "nmt",
  "outputs": [{
    "name": "OUTPUT_TEXT",
    "data": ["नमस्ते, आप कैसे हैं?"]
  }]
}
```

> **The first inference request may take 1–3 minutes** while the model downloads into `hf-cache`. Subsequent requests are faster.

**Do not proceed to Part B until this curl returns HTTP 200 with Hindi text.**

---

## Part B — AI4I-Orchestrate platform

All commands below run from the `ai4i-core` repo root unless stated otherwise.

**If `$AI4I_LOCAL` is unset** (e.g. you opened a new terminal), set it first:

```bash
export AI4I_LOCAL=~/ai4i-local-setup   # same path as in §3
cd "$AI4I_LOCAL/ai4i-core"
```

If `cd` fails with “No such file or directory”, fix `AI4I_LOCAL` or complete [§3](#3-clone-repositories) first.

### B1. Create root `.env`

```bash
cp env.template .env
```

Open the file in an editor and update the placeholder values. **Keep all other lines** from `env.template` (do not replace the file with only the four lines below — that breaks migrations).

```bash
nano .env
# or: vi .env
```

Find and set these values (others can stay at their defaults):

```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
REDIS_PASSWORD=changeme
TRITON_ENDPOINT_NMT=http://localhost:8000
```

Replace the template placeholders, e.g. change `POSTGRES_USER=<YOUR_POSTGRES_USER>` to `POSTGRES_USER=postgres`, and `REDIS_PASSWORD=<YOUR_REDIS_PASSWORD>` to `REDIS_PASSWORD=changeme`. Leave lines such as `ALEMBIC_DB_HOST=localhost` and `ALEMBIC_DB_PORT=5432` unchanged.

> **Other model servers besides NMT:** the seed migration in [B5](#b5-run-database-migrations) reads one `TRITON_ENDPOINT_*` variable per service (ASR, OCR, NER, TTS, LLM, etc.) and leaves the `endpoint` blank for anything not set here. If you already have one of those servers running, add its variable now (e.g. `TRITON_ENDPOINT_ASR=http://localhost:5000`) — otherwise fill it in later via [C4](#c4-set-an-inference-service-endpoint-after-migration).

**Alternative — set values with `sed` after `cp`:**

```bash
sed -i \
  -e 's/POSTGRES_USER=<YOUR_POSTGRES_USER>/POSTGRES_USER=postgres/' \
  -e 's/POSTGRES_PASSWORD=<YOUR_POSTGRES_PASSWORD>/POSTGRES_PASSWORD=postgres/' \
  -e 's/REDIS_PASSWORD=<YOUR_REDIS_PASSWORD>/REDIS_PASSWORD=changeme/' \
  .env
echo 'TRITON_ENDPOINT_NMT=http://localhost:8000' >> .env
grep -E '^(POSTGRES_|REDIS_|TRITON_|ALEMBIC_)' .env
```

### B2. Generate per-service environment files

```bash
./scripts/setup-env.sh
```

**Expected:**

```
Done — 5 .env file(s) generated.
```

Creates `.env` files for auth, platform-core, inference, frontend, and Alembic.

### B3. Start Docker infrastructure (minimal)

Only PostgreSQL and Redis are required:

```bash
docker compose -f docker-compose-local.yml up -d postgres redis
```

Wait until healthy:

```bash
docker compose -f docker-compose-local.yml ps
```

**Expected:**

| Service | Status |
|---------|--------|
| `ai4v-postgres` | Up **(healthy)** |
| `ai4v-redis` | Up **(healthy)** |

### B4. Install migration dependencies

From the `ai4i-core` repo root, create a virtualenv and install Alembic dependencies:

```bash
cd "$AI4I_LOCAL/ai4i-core"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip --version    # must succeed inside the venv

cd infrastructure/databases
python3 -m pip install -r requirements.txt
cd ../..
```

> Keep this venv activated for [B5](#b5-run-database-migrations). Part C services use **separate** `.venv` folders inside each `services/*` directory.

### B5. Run database migrations

```bash
cd "$AI4I_LOCAL/ai4i-core"
source .venv/bin/activate    # if not already active
./scripts/migrate.sh all upgrade
```

**Expected:** migrations apply for `ai4iplatform_auth`, `ai4i_platform_db`, and `ai4iplatform_core` without errors.

**Default admin credentials** (created by migration seed):

| Field | Value |
|-------|-------|
| Username | `admin` |
| Email | `admin@ai4inclusion.org` |
| Password | `ADMIN_PASSWORD` (literal string) |

---

## Part C — Application services

Open **three separate terminals**. Each service needs its own virtualenv.

> **Important:** `ai4i-core` is published on public PyPI — see [ai4i-core on Libraries.io](https://libraries.io/pypi/ai4i-core). Each service’s `requirements.txt` installs it automatically via `python3 -m pip install -r requirements.txt`.

> The repo-root `.venv` from [B4](#b4-install-migration-dependencies) is for migrations only. Part C still needs a **separate** `.venv` inside each `services/*` folder (do not reuse the migration venv for uvicorn).

If `$AI4I_LOCAL` is unset, run `export AI4I_LOCAL=~/ai4i-local-setup` first (see [§3](#3-clone-repositories) or [Part B](#part-b--ai4i-orchestrate-platform)).

### C1. Auth service (port 8081) — Terminal 1

Run **one command per line** (do not paste multiple lines together):

```bash
export AI4I_LOCAL=~/ai4i-local-setup
cd "$AI4I_LOCAL/ai4i-core/services/auth-service"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

**Expected:** `Application startup complete`  
**Verify:** http://localhost:8081/docs

### C2. Platform core service (port 8095) — Terminal 2

```bash
export AI4I_LOCAL=~/ai4i-local-setup
cd "$AI4I_LOCAL/ai4i-core/services/platform-core-service"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload
```

**Expected:** `Application startup complete`  
**Verify:** http://localhost:8095/docs

### C3. Inference service (port 8090) — Terminal 3

```bash
export AI4I_LOCAL=~/ai4i-local-setup
cd "$AI4I_LOCAL/ai4i-core/services/inference-service"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

**Expected:** `Application startup complete`  
**Verify:** http://localhost:8090/docs

**Harmless warnings on minimal infra:**

- `KafkaConnectionError: localhost:9093` — Kafka is not started (Option A infra). Tracing falls back to logs. **NMT still works.**
- `Couldn't find ffmpeg` — only affects ASR/TTS, not NMT.

### C4. Set an inference service endpoint after migration

Skip this for any service whose `TRITON_ENDPOINT_*` var you already set in [B1](#b1-create-root-env) — it was seeded with the endpoint filled in. Use this for any service whose var was never added to root `.env` in the first place, one you bring online later, or to fix an endpoint that changed.

Look up the `serviceId` first, then patch its endpoint — the update call is keyed by `serviceId`, not by name. `PATCH /api/v1/services` takes a `"services"` array — pass one entry to update a single service, or several to update them all in one call.

```bash
curl -s "http://localhost:8095/api/v1/services?task_type=asr" | python3 -m json.tool
```

Grab the `serviceId` of the service(s) you want from the response, then:

```bash
curl -s -X PATCH http://localhost:8095/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "services": [
      {"serviceId": "<serviceId-from-above>", "endpoint": "http://<model-server-host>:5000"}
    ]
  }'
```

To set several endpoints in one call, just add more entries:

```bash
curl -s -X PATCH http://localhost:8095/api/v1/services \
  -H "Content-Type: application/json" \
  -d '{
    "services": [
      {"serviceId": "<serviceId-1>", "endpoint": "http://<model-server-host>:5000"},
      {"serviceId": "<serviceId-2>", "endpoint": "http://<model-server-host>:8000"}
    ]
  }'
```

**Expected:** `{"success":true, "data":{"serviceIds":["<serviceId-1>", ...]}, ... "message":"N service endpoint(s) updated successfully."}`

`<model-server-host>` must be a real, non-loopback, routable address (e.g. the host's LAN IP or a resolvable DNS name) — the SSRF guard unconditionally rejects `localhost`/loopback and private IPs, with no opt-out, so those values will always fail here even if the model server is actually listening there. This call also probes each endpoint live before accepting it, so start the model server(s) first — a `400` here almost always means one isn't reachable yet at that address. The call is all-or-nothing — if one entry fails (unreachable endpoint, loopback/private IP blocked by the SSRF guard, unknown `serviceId`), none of the endpoints in the request are updated. No `Authorization` header is needed for this native, non-gateway setup.

---

## Part D — Verify end-to-end NMT

### D1. Health check

```bash
curl -s http://localhost:8090/health
```

**Expected:** `{"status":"healthy"}`

### D2. Translate via inference-service

> **The first inference request may take 1–3 minutes** while the model loads or downloads weights. Wait for the response before assuming failure.

```bash
curl -s -X POST http://localhost:8090/api/v1/nmt/inference \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"source": "Hello, how are you?"}],
    "config": {
      "serviceId": "de9a4570f8c14f6859cb79c1934a4db9",
      "language": {"sourceLanguage": "en", "targetLanguage": "hi"}
    }
  }'
```

**Expected:**

```json
{
  "output": [{
    "source": "Hello, how are you?",
    "target": "नमस्ते, आप कैसे हैं?"
  }],
  "smr_response": null
}
```

### D3. Obtain an access token (Bearer)

UI requests use a **JWT access token** in the `Authorization: Bearer` header — not an API key. Log in directly against auth-service (the same endpoint the Simple UI proxy calls):

```bash
LOGIN=$(curl -s -X POST http://localhost:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}')

echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'access_token' in d, d"

export TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

**Expected:** `LOGIN` JSON includes `"access_token"` and `"refresh_token"`. `echo ${#TOKEN}` should print a large number (hundreds of characters).

If login fails, confirm auth-service is up on `:8081` (see [Part E](#part-e--frontend-optional)).

### D4. Translate with a Bearer token

Uses the token from [D3](#d3-obtain-an-access-token-bearer). Calls inference-service directly on `:8090`.

> **The first inference request may take 1–3 minutes** while the model loads or downloads weights.

```bash
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

**Expected:** Same translated `output` as [D2](#d2-translate-via-inference-service).

---

## Part E — Frontend (optional)

### E1. Configure and run Simple UI

The file `frontend/simple-ui/.env` was created in [B2](#b2-generate-per-service-environment-files) by `./scripts/setup-env.sh`. Confirm the API URL points at the Next.js dev server (no API key is required — the UI uses **Bearer JWT** after sign-in):

```bash
export AI4I_LOCAL=~/ai4i-local-setup
cd "$AI4I_LOCAL/ai4i-core/frontend/simple-ui"

grep NEXT_PUBLIC_API_URL .env
# Expected: NEXT_PUBLIC_API_URL=http://localhost:3000
```

If needed, open `.env` in an editor (`nano .env` or `vi .env`) and set `NEXT_PUBLIC_API_URL=http://localhost:3000`. Leave other lines at their defaults.

Install dependencies and start the UI:

```bash
cd "$AI4I_LOCAL/ai4i-core/frontend/simple-ui"
npm install
npm run dev
```

Open **http://localhost:3000** in your browser.

**How browser API calls are routed:** The UI is configured with `NEXT_PUBLIC_API_URL=http://localhost:3000`. Every API call from the browser (sign-in, NMT, etc.) goes to the Next.js dev server on port 3000, where the catch-all API route `src/pages/api/v1/[...proxy].ts` does path routing, forward-auth (calling auth-service `/api/v1/auth/validate`), and proxies to the backend services (auth `:8081`, platform-core `:8095`, inference `:8090`). There is no separate gateway to run — the backend services and the Next.js dev server just need to be up.

### E2. Sign in on the UI

After the page loads, you should see the **Sign in** screen (or go to **http://localhost:3000/auth**).

Use the default admin account created by migrations ([B5](#b5-run-database-migrations)):

| Field | Value |
|-------|-------|
| **Email** | `admin@ai4inclusion.org` |
| **Password** | `ADMIN_PASSWORD` (type the literal string, not a custom password) |

1. Enter **Email** and **Password** in the form.
2. Click **Sign in**.
3. On success, you are redirected to the home page and can open **NMT** (or other services) from the menu.

If sign-in fails, confirm auth-service (`:8081`), the Next.js dev server (`:3000`), and migrations ([B5](#b5-run-database-migrations)) are complete before changing credentials.

---

## Port reference

| Service | URL | Where it runs |
|---------|-----|---------------|
| NMT Triton (`indictrans`) | http://localhost:8000 | Docker |
| Auth service | http://localhost:8081/docs | Native (uvicorn) |
| Inference service | http://localhost:8090/docs | Native (uvicorn) |
| Platform core | http://localhost:8095/docs | Native (uvicorn) |
| Simple UI | http://localhost:3000 | Native (Next.js) |
| PostgreSQL | localhost:5432 | Docker |
| Redis | localhost:6379 | Docker |

### NMT API constants

| Item | Value |
|------|-------|
| Seeded service name | `indictrans-gpu-t4` |
| Service ID (API `config.serviceId`) | `de9a4570f8c14f6859cb79c1934a4db9` |
| Triton model name | `nmt` |
| Triton infer URL | `http://localhost:8000/v2/models/nmt/infer` |

---

## Stopping and restarting

### Stop application services

Press `Ctrl+C` in each terminal running uvicorn.

### Stop Docker infrastructure

```bash
cd "$AI4I_LOCAL/ai4i-core"
docker compose -f docker-compose-local.yml down
```

### Stop NMT

```bash
docker stop indictrans
```

### Full restart (keep data)

```bash
# NMT
docker start indictrans

# Infra
cd "$AI4I_LOCAL/ai4i-core"
docker compose -f docker-compose-local.yml up -d postgres redis

# Then start auth :8081, platform-core :8095, inference :8090 (Part C)
```

### Fresh start (wipe all platform data)

```bash
cd "$AI4I_LOCAL/ai4i-core"
docker compose -f docker-compose-local.yml down -v
# Re-run Part B from B3 onward (migrations will re-seed everything)
```

---

## Troubleshooting

### NMT

| Symptom | Fix |
|---------|-----|
| `docker build ... requires 1 argument` | Run `docker build -t nmt-triton-cpu .` from inside `nmt-triton/` (note the `.`) |
| Port 8000 already in use | `docker ps` / `lsof -i :8000` — stop conflicting container or process |
| `container name indictrans already in use` | `docker rm -f indictrans` then re-run |
| `401 gated repo` on first translate | Accept model access on HuggingFace; pass `-e HF_TOKEN=hf_...` |
| First request very slow | One-time model download — watch `docker logs -f indictrans` |

### AI4I-Orchestrate

| Symptom | Fix |
|---------|-----|
| `cd: .../ai4i-core/services/auth-service: No such file or directory` | `AI4I_LOCAL` is unset or wrong. Run `export AI4I_LOCAL=~/ai4i-local-setup` (adjust path), then `cd "$AI4I_LOCAL/ai4i-core/services/auth-service"`. Remove a mistaken root venv: `rm -rf ~/ai4i-local-setup/ai4i-core/.venv` |
| Authenticated NMT returns `401` / unauthorized | Run [D3](#d3-obtain-an-access-token-bearer) to get a fresh `TOKEN`; pass `Authorization: Bearer $TOKEN` as in [D4](#d4-translate-with-a-bearer-token) |
| Cloned `ai4i-core` from `master` / `main` by mistake | Re-clone with `--branch <release-tag>` from [ai4i-core releases](https://github.com/COSS-India/ai4i-core/releases), or `git fetch --tags && git checkout <release-tag>` |
| `alembic/.env: line 6: syntax error near unexpected token 'newline'` | Root `.env` was overwritten with only a few lines, so `setup-env.sh` left placeholders like `<ALEMBIC_DB_HOST>` in `infrastructure/databases/migrations/postgres/alembic/.env`. Fix: `cp env.template .env`, edit placeholders (see B1), run `./scripts/setup-env.sh` again, then `./scripts/migrate.sh all upgrade` |
| Migration: `password authentication failed for user postgres` / `Role postgres does not exist` | Stale Postgres volume from old install. Run `docker compose -f docker-compose-local.yml down -v`, restart infra (B3), re-run migrations (B5) |
| `No matching distribution found for ai4i-core` | Install from PyPI: `python3 -m pip install ai4i-core` — see [libraries.io/pypi/ai4i-core](https://libraries.io/pypi/ai4i-core) |
| `python3: command not found` or version below 3.11 | Install Python >= 3.11 (see [§1](#1-system-prerequisites)); confirm with `python3 --version` |
| Inference: `KafkaConnectionError` | Expected without Kafka; NMT unaffected |
| NMT via inference returns 502 / upstream failed | Ensure `indictrans` is running; verify Part A5 curl works |
| NMT endpoint wrong | Set `TRITON_ENDPOINT_NMT=http://localhost:8000` in `.env` before migrations; if already migrated, run `docker compose down -v` and re-run Part B |
| Other service (ASR/OCR/NER/TTS/LLM/...) has a blank endpoint | Its `TRITON_ENDPOINT_*` var wasn't set before migrating. Fix via [C4](#c4-set-an-inference-service-endpoint-after-migration) once its model server is running |
| Admin login fails (wrong password) | Email `admin@ai4inclusion.org`, password literal `ADMIN_PASSWORD` |

### Supported NMT languages

Short codes: `en`, `hi`, `bn`, `ta`, `te`, `mr`, `gu`, `kn`, `ml`, `pa`, `or`, `as`, and others — see `SHORT_TO_FLORES` in `model-hosting/nmt-triton/models/nmt/1/model.py`. English ↔ any Indic; any Indic ↔ any Indic.

---

## Setup complete checklist

- [ ] Cloned `ai4i-core` (release tag) and `model-hosting` (`feat/nmt-local-setup`) into `~/ai4i-local-setup`
- [ ] `docker ps` shows `indictrans` on port 8000
- [ ] Part A5 curl returns Hindi translation
- [ ] `docker compose ps` shows postgres + redis healthy
- [ ] `./scripts/migrate.sh all upgrade` completed
- [ ] Auth, platform-core, inference show `Application startup complete`
- [ ] Part D2 curl returns translated `target` field
- [ ] Part D3 login returns `access_token`; Part D4 authenticated curl returns translated `target` field

When all boxes are checked, your local AI4I-Orchestrate + NMT stack is fully operational.

---

## Other model services

Additional local model guides: **[model-hosting](https://github.com/COSS-India/model-hosting)** (`feat/nmt-local-setup`) — see [README](https://github.com/COSS-India/model-hosting/blob/feat/nmt-local-setup/README.md) and `setup-docs/`.

---

## Tracing and observability

Optional full stack (Kafka, OpenSearch, Prometheus, Grafana): **`docs/TRACING-OBSERVABILITY-LOCAL-SETUP.md`** in this repo. The minimal setup in Parts B–C does not require it.

---

## Related documents

| Document | Link |
|----------|------|
| This guide | [END-TO-END-SETUP-GUIDE.md](END-TO-END-SETUP-GUIDE.md) |
| Tracing and observability (local) | [TRACING-OBSERVABILITY-LOCAL-SETUP.md](TRACING-OBSERVABILITY-LOCAL-SETUP.md) |
| Docker Compose local reference | [DOCKER-COMPOSE-LOCAL-REFERENCE.md](DOCKER-COMPOSE-LOCAL-REFERENCE.md) |
| model-hosting | [github.com/COSS-India/model-hosting](https://github.com/COSS-India/model-hosting) (`feat/nmt-local-setup`) |
| ai4i-core (PyPI) | [libraries.io/pypi/ai4i-core](https://libraries.io/pypi/ai4i-core) |
