# AI4I-Core Microservices Platform

> **Open-source codebase** for building AI/ML microservices for Indic languages.
> Not a hosted service — you deploy and manage it yourself.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Issues](https://img.shields.io/github/issues/COSS-India/ai4i-core)](https://github.com/COSS-India/ai4i-core/issues)
[![GitHub Stars](https://img.shields.io/github/stars/COSS-India/ai4i-core)](https://github.com/COSS-India/ai4i-core/stargazers)

---

## 🎯 What This Repository Provides

An open-source, **FastAPI**-based reference implementation for deploying multi-tenant
**language-AI services** (translation, speech, OCR, NER, LLM) in your own infrastructure.

## 🏗️ Architecture Overview

The platform is **three application microservices** behind an APISIX gateway, sharing a
PostgreSQL/Redis data plane. Inference trace spans flow out on a **separate observability
lane** (dotted) so they never touch the business-data path.

![Architecture overview — Portal → APISIX → auth / platform-core / inference, with the telemetry lane to OpenSearch](./docs/images/architecture.png)

<!-- Source: docs/images/architecture.mmd — regenerate with:
     npx @mermaid-js/mermaid-cli -i docs/images/architecture.mmd -o docs/images/architecture.png -b white -s 2 -->

> **Solid** arrows = request / business-data path; **dotted** = cache and the telemetry
> lane. Full diagrams (system, request sequence, telemetry lane) and code references:
> **[docs/architecture/00-overview.md](./docs/architecture/00-overview.md)** — start here.
> Every external request is authorized at the gateway via auth-service `/auth/validate`
> (forward-auth), which returns identity headers (`X-User-ID`, `X-Tenant-ID`) the
> downstream service trusts.

## 📦 What's Included

- ✅ **Source code** for all backend services and the frontend
- ✅ **Docker Compose** (`docker-compose-local.yml`) for local infrastructure
- ✅ **Alembic migrations** for the PostgreSQL schemas
- ✅ **Shared Python library** (`libs/ai4icore_core`): logging + request middleware,
  observability (OpenTelemetry + Prometheus ASGI), bootstrap (API versioning, async DB),
  email, exceptions, request-scoped context
- ✅ **Code-anchored documentation** — every non-obvious claim links to a source path

> **Note on gateways:** the production infrastructure uses
> **APISIX** (external to this repo). The **local development setup**
> defined by `docker-compose-local.yml` uses an **nginx** stand-in
> (`nginx-gateway`, image `nginx:alpine`, config at
> `infrastructure/nginx/nginx.conf`) so the same forward-auth contract can
> be exercised without standing up APISIX. See
> [`docs/SETUP_GUIDE.md`](./docs/SETUP_GUIDE.md) for local-setup specifics.

## 🎯 Core Services

The AI/ML capabilities (NMT, ASR, TTS, NER, OCR, …) are **consolidated into a single
`inference-service`**, not separate per-modality services.

| Service | Port | Database | Purpose | Docs |
|---------|------|----------|---------|------|
| **auth-service** | `8081` | PostgreSQL `ai4iplatform_auth` | AuthN/AuthZ, users, tenants, RBAC, API keys, OAuth2; issues & validates JWTs | [README](./services/auth-service/README.md) · [Architecture](./docs/architecture/01-auth-service.md) |
| **platform-core-service** | `8095` | PostgreSQL `ai4iplatform_core` | Model & service registry, alerts, telemetry (trace) query | [README](./services/platform-core-service/README.md) · [Architecture](./docs/architecture/02-platform-core-service.md) |
| **inference-service** | `8090` | stateless | Unified inference orchestration over Triton / OpenAI-compatible backends (tasks below) | [README](./services/inference-service/README.md) · [Architecture](./docs/architecture/03-inference-service.md) |

> In local development all three application services run **natively** on the host (Docker
> hosts only the infrastructure). The `docker-compose-local.yml` file also includes
> container definitions for them, used by the alternative all-in-Docker workflow in
> `docs/SETUP_GUIDE.md` (where platform-core is published on host `8102`).

### Inference services

All inference services share one unified endpoint `POST /api/v1/inference` (routed by
`task_type`), each also exposed as a per-service alias `POST /api/v1/{task}/inference`. LLM
uses an OpenAI-compatible `POST /api/v1/chat/completions`.

| Service | `task_type` | Endpoint | Description |
|---------|-------------|----------|-------------|
| Machine Translation | `NMT` | `/api/v1/nmt/inference` | Neural machine translation |
| Speech Recognition | `ASR` | `/api/v1/asr/inference` | Speech → text |
| Text-to-Speech | `TTS` | `/api/v1/tts/inference` | Text → audio |
| Named Entity Recognition | `NER` | `/api/v1/ner/inference` | Entity extraction |
| OCR | `OCR` | `/api/v1/ocr/inference` | Image → text |
| Transliteration | `TRANSLITERATION` | `/api/v1/transliteration/inference` | Script transliteration |
| Language Detection | `LANGUAGE_DETECTION` | `/api/v1/language-detection/inference` | Text language identification |
| Audio Language Detection | `AUDIO_LANGUAGE_DETECTION` | `/api/v1/audio-lang-detection/inference` | Spoken-language identification |
| Speaker Diarization | `SPEAKER_DIARIZATION` | `/api/v1/speaker-diarization/inference` | Who-spoke-when segmentation |
| Language Diarization | `LANGUAGE_DIARIZATION` | `/api/v1/language-diarization/inference` | Multilingual audio segmentation |
| LLM Chat | — | `/api/v1/chat/completions` | OpenAI-compatible chat completions |

> Source of truth: `services/inference-service/orchestrator/task_service_registry.py`
> (`GET /api/v1/inference/tasks` lists what the running service has registered).

**PII detection & redaction is NOT served by the inference-service.** It lives in
**platform-core-service** (control plane) under `/api/v1/pii/*` — domain
policies, regex patterns, tenant-domain mappings, audit logs, and the
`redact-text` endpoint. Source:
`services/platform-core-service/app/routes/pii.py`. The `PIITaskService` stub
that still appears in `task_service_registry.py` is a 501 placeholder kept so
PII inference requests fail loudly instead of falling through.

## 🎨 Frontend

- **Simple UI** (`frontend/simple-ui`, port `3000`) — web interface built with **Next.js 14**,
  **React 18**, and **TypeScript** for exercising the platform's APIs.

## 🛠️ Technology Stack

### Backend
- **FastAPI** · **Python 3.11** — async microservices
- **PostgreSQL 15** — primary relational store (per-service databases)
- **Redis 7** — cache, rate-limit/session state, resolution cache
- **SQLAlchemy (async)** + **Alembic** — ORM & migrations
- **Pydantic** — validation/serialization
- **NVIDIA Triton** / OpenAI-compatible **LLM** backends — model serving

### Frontend
- **Next.js 14** · **React 18** · **TypeScript** · **zod**

### Gateway & Infrastructure
- **APISIX** — API gateway in production / staging / dev (forward-auth via `/auth/validate`; external to this repo). For local development, `docker-compose-local.yml` provides an **nginx** stand-in (`nginx-gateway`, config at `infrastructure/nginx/nginx.conf`).
- **Docker Compose** — local infrastructure (`docker-compose-local.yml`)
- **Kafka + Zookeeper** — OpenTelemetry span transport (telemetry lane)
- **Prometheus · Grafana · Alertmanager · Node Exporter** — metrics & alerting
- **OpenSearch + Dashboards · Fluent Bit** — logs & trace (`traces-*`) storage

## 🚀 Deploy Your Own Instance

### Prerequisites
Docker runs the **infrastructure only**; the application services run **natively** on the host.
- **Docker 20.10+ / Docker Compose 2.0+** — for infrastructure (PostgreSQL, Redis, Kafka, OpenSearch, Prometheus, …)
- **Python 3.11 + pip** — for the application services (auth, platform-core, inference)
- **Node 18+** — for the Simple UI frontend
- ~16 GB RAM recommended for the full stack; Linux / macOS (Windows via WSL2)

### Quick Start (local)
```bash
# 1. Clone
git clone https://github.com/COSS-India/ai4i-core.git
cd ai4i-core

# 2. Configure environment (see docs/SETUP_GUIDE.md for the full walkthrough)
./scripts/setup-env.sh

# 3. Start INFRASTRUCTURE in Docker (not the app services)
#    (add opensearch fluent-bit prometheus grafana for the full observability stack)
docker compose -f docker-compose-local.yml up -d postgres redis kafka zookeeper

# 4. Run database migrations — see docs/SETUP_GUIDE.md, Step 5

# 5. Run each application service NATIVELY (separate terminals)
cd services/auth-service          && pip install -r requirements.txt && uvicorn app.main:app --port 8081
cd services/platform-core-service && pip install -r requirements.txt && uvicorn app.main:app --port 8095
cd services/inference-service     && pip install -r requirements.txt && python main.py          # :8090

# 6. Run the frontend natively
cd frontend/simple-ui && npm install && npm run dev                                              # :3000
```
> Full instructions: **[docs/SETUP_GUIDE.md](./docs/SETUP_GUIDE.md)**.

### Service URLs (local)
| URL | What |
|-----|------|
| http://localhost:3000 | Portal (Simple UI) |
| http://localhost:8081 | auth-service |
| http://localhost:8095 | platform-core-service |
| http://localhost:8090 | inference-service |
| http://localhost:3001 | Grafana |
| http://localhost:9090 | Prometheus |
| http://localhost:5602 | OpenSearch Dashboards |

## 📖 Documentation

### Architecture (code-anchored)
- [docs/architecture/00-overview.md](./docs/architecture/00-overview.md) — system overview (**start here**)
- [docs/architecture/01-auth-service.md](./docs/architecture/01-auth-service.md) — auth/RBAC, tenants, API keys, OAuth2, JWT
- [docs/architecture/02-platform-core-service.md](./docs/architecture/02-platform-core-service.md) — model/service registry, alerts, telemetry query
- [docs/architecture/03-inference-service.md](./docs/architecture/03-inference-service.md) — inference orchestration over Triton/LLM

### Setup
- [docs/SETUP_GUIDE.md](./docs/SETUP_GUIDE.md) — comprehensive local setup

### Service READMEs
- [auth-service](./services/auth-service/README.md) · [platform-core-service](./services/platform-core-service/README.md) · [inference-service](./services/inference-service/README.md)

## 🤝 Contributing

1. Branch off `dev` (`git checkout -b feat/your-change origin/dev`)
2. Make changes following the existing patterns; keep migrations single-headed
   (validated by `scripts/validate-migrations.py`, run as a pre-commit hook)
3. Open a Pull Request against `dev`

## 📊 Monitoring & Observability

- **Metrics** — services expose Prometheus metrics (scraped by **Prometheus**,
  visualized in **Grafana**, alerted via **Alertmanager**).
- **Logs** — structured JSON logs (`ai4icore_core.logging`) shipped by **Fluent Bit** to
  **OpenSearch**.
- **Traces** — only **inference-service** emits OpenTelemetry spans; they flow
  **Kafka (`kafka-topic-otel-trace`) → Fluent Bit → OpenSearch `traces-*`**, queried via
  platform-core's `/telemetry/traces/search`.

![Observability pipeline — logs from all services and traces from inference flow through Fluent Bit into OpenSearch logs-* / traces-*](./docs/images/observability.png)

<!-- Source: docs/images/observability.mmd — regenerate with:
     npx @mermaid-js/mermaid-cli -i docs/images/observability.mmd -o docs/images/observability.png -b white -s 2 -->

> **Logs** (thin arrows): every service writes structured JSON to stdout → **Fluent Bit**
> tails it → OpenSearch **`logs-*`**. **Traces** (thick arrows): inference-service spans →
> **Kafka** → Fluent Bit (`in_kafka`, lifts the span payload) → OpenSearch **`traces-*`**.
> Both are viewable in **OpenSearch Dashboards**; platform-core reads `traces-*` for the
> trace API. Metrics go the separate Prometheus → Grafana/Alertmanager route.

## 📄 License

Licensed under the **MIT License** — see [LICENSE](./LICENSE).

## 💬 Community & Support

Open-source project — support is community-based:
- **Issues:** [GitHub Issues](https://github.com/COSS-India/ai4i-core/issues)
- **Docs:** the [`docs/`](./docs/) directory
- **Debugging:** infrastructure logs via `docker compose -f docker-compose-local.yml logs <service>`;
  app-service logs appear in the terminal running each service; check per-service `/health` endpoints

> Provided as-is; no commercial SLA.
