# AI4I-Core Microservices Platform

> **Open-source codebase** for building enterprise-grade AI/ML microservices for Indic
> languages. Not a hosted service — you deploy and manage it yourself.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Issues](https://img.shields.io/github/issues/COSS-India/ai4i-core)](https://github.com/COSS-India/ai4i-core/issues)
[![GitHub Stars](https://img.shields.io/github/stars/COSS-India/ai4i-core)](https://github.com/COSS-India/ai4i-core/stargazers)

---

## 🎯 What This Repository Provides

An open-source platform codebase built with **FastAPI**, providing a reference
implementation for deploying scalable language-AI services. A web **Portal** talks to a
set of microservices through an **APISIX** gateway; services persist business data in
**PostgreSQL** and use **Redis** for caching and session/rate-limit state. Observability
data flows on a separate lane via **Kafka → Fluent Bit → OpenSearch** plus
**Prometheus/Grafana**.

**What you get:** complete source for the services, frontend, and shared libraries; Docker
Compose for local infrastructure; Alembic migrations; and code-anchored architecture docs.

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

## 📦 What This Repository Provides

- ✅ **Source code** for all backend services and the frontend
- ✅ **Docker Compose** (`docker-compose-local.yml`) for local infrastructure
- ✅ **Alembic migrations** for the PostgreSQL schemas
- ✅ **Shared Python library** (`libs/ai4icore_core`): logging + request middleware,
  observability (OpenTelemetry + Prometheus ASGI), bootstrap (API versioning, async DB),
  email, exceptions, request-scoped context
- ✅ **Code-anchored documentation** — every non-obvious claim links to a source path

> **Note:** this is **not a hosted service**. You deploy and manage it in your own
> infrastructure. The APISIX gateway is **external to this repo** (not in compose).

## 🎯 Core Services

The AI/ML capabilities (NMT, ASR, TTS, NER, OCR, …) are **consolidated into a single
`inference-service`**, not separate per-modality services.

| Service | Port | Database | Purpose | Docs |
|---------|------|----------|---------|------|
| **auth-service** | `8081` | PostgreSQL `ai4iplatform_auth` | AuthN/AuthZ, users, tenants, RBAC, API keys, OAuth2; issues & validates JWTs | [README](./services/auth-service/README.md) · [Architecture](./docs/architecture/01-auth-service.md) |
| **platform-core-service** | `8095` (host `8102`) | PostgreSQL `ai4iplatform_core` | Model & service registry, alerts, telemetry (trace) query | [README](./services/platform-core-service/README.md) · [Architecture](./docs/architecture/02-platform-core-service.md) |
| **inference-service** | `8090` (runs natively) | stateless | Unified inference orchestration over Triton / OpenAI-compatible backends (tasks below) | [README](./services/inference-service/README.md) · [Architecture](./docs/architecture/03-inference-service.md) |

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
| PII | `PII` | `/api/v1/inference` (`task_type=PII`) | PII detection / redaction |
| LLM Chat | — | `/api/v1/chat/completions` | OpenAI-compatible chat completions |

> Source of truth: `services/inference-service/orchestrator/task_service_registry.py`
> (`GET /api/v1/inference/tasks` lists what the running service has registered).

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
- **APISIX** — API gateway (forward-auth via `/auth/validate`; external to this repo)
- **Docker Compose** — local infrastructure (`docker-compose-local.yml`)
- **Kafka + Zookeeper** — OpenTelemetry span transport (telemetry lane)
- **Prometheus · Grafana · Alertmanager · Node Exporter** — metrics & alerting
- **OpenSearch + Dashboards · Fluent Bit** — logs & trace (`traces-*`) storage
- **Jaeger** — bundled in the local compose stack

## 🚀 Deploy Your Own Instance

### Prerequisites
- Docker 20.10+ and Docker Compose 2.0+
- ~16 GB RAM recommended to run the full stack locally
- Linux / macOS (Windows via WSL2)

### Quick Start (local)
```bash
# 1. Clone
git clone https://github.com/COSS-India/ai4i-core.git
cd ai4i-core

# 2. Configure environment (see docs/SETUP_GUIDE.md for the full walkthrough)
./env-local-setup/setup-env.sh

# 3. Start infrastructure + compose-managed services
docker compose -f docker-compose-local.yml up -d

# 4. inference-service runs natively on the host
cd services/inference-service && pip install -r requirements.txt && python main.py

# 5. Open the UI
open http://localhost:3000
```
> Full instructions: **[docs/SETUP_GUIDE.md](./docs/SETUP_GUIDE.md)**.

### Service URLs (local)
| URL | What |
|-----|------|
| http://localhost:3000 | Portal (Simple UI) |
| http://localhost:8081 | auth-service |
| http://localhost:8102 | platform-core-service (container `8095`) |
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
  platform-core's `/telemetry/traces/search`. (Jaeger is available in the local compose
  stack.)

![Observability pipeline — logs from all services and traces from inference flow through Fluent Bit into OpenSearch logs-* / traces-*](./docs/images/observability.png)

<!-- Source: docs/images/observability.mmd — regenerate with:
     npx @mermaid-js/mermaid-cli -i docs/images/observability.mmd -o docs/images/observability.png -b white -s 2 -->

> **Logs** (thin arrows): every service writes structured JSON to stdout → **Fluent Bit**
> tails it → OpenSearch **`logs-*`**. **Traces** (thick arrows): inference-service spans →
> **Kafka** → Fluent Bit (`in_kafka`, lifts the span payload) → OpenSearch **`traces-*`**.
> Both are viewable in **OpenSearch Dashboards**; platform-core reads `traces-*` for the
> trace API. Metrics go the separate Prometheus → Grafana/Alertmanager route.

## 📄 License

Licensed under the **MIT License**. You are free to use, modify, and distribute this code,
including commercially, with no warranty or liability from the maintainers.

## 💬 Community & Support

Open-source project — support is community-based:
- **Issues:** [GitHub Issues](https://github.com/COSS-India/ai4i-core/issues)
- **Docs:** the [`docs/`](./docs/) directory
- **Deployment debugging:** `docker compose -f docker-compose-local.yml logs <service>` and
  per-service `/health` endpoints

> Provided as-is; no commercial SLA.

## 🙏 Acknowledgments

Built with open-source technologies — FastAPI, PostgreSQL, Redis, Kafka, APISIX,
Prometheus, Grafana, OpenSearch, Fluent Bit, Next.js / React / TypeScript, and the
NVIDIA Triton Inference Server — and the **AI4Bharat** Indic-language models served
through it.
