# Third-Party Service Providers

This document catalogs the external **services, platforms, and infrastructure providers** the ai4i-core platform actually integrates with — as distinct from [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md), which lists code-level library dependencies and their licenses.

Providers are split into **Paid/Commercial SaaS**, **Free (Commercial, No Cost)**, and **Open Source** (self-hosted or library). Only services with real, active usage in this repo are listed — unused/scaffold-only integrations (e.g. env vars referenced by empty stub services) are omitted.

> Scope note: real, tracked source code lives in `services/auth-service`, `services/platform-core-service`, `services/inference-service`, `services/kafka-consumers`, `libs/ai4i_core`, and `frontend/simple-ui`.

---

## Paid / Commercial SaaS

| Provider | Category | Use | Citation |
|---|---|---|---|
| **AWS (Amazon Web Services)** | Cloud Infrastructure | Hosts all deployments and servers — EC2 (or equivalent) instances backing the environment, including the externally-reachable Triton inference endpoints seeded into the DB | `.env` / `dev.secrets.example` (`TRITON_ENDPOINT_ASR=http://13.200.133.97:5000`, `TRITON_ENDPOINT_LLM=http://52.200.236.126:8001`, etc. — AWS-range IPs) |
| **Amazon SES** | Email | Transactional email (verification, password reset, setup links) — the codebase's SMTP client is provider-agnostic, but the configured credentials/host point at SES | `libs/ai4i_core/ai4i_core/email/providers/smtp.py`, `services/auth-service/env.template:86-105` |
| **Google OAuth 2.0** | Auth | "Sign in with Google" identity provider | `services/auth-service/app/services/oauth_service.py`, `services/auth-service/env.template:70-77` |

---

## Free (Commercial, No Cost)

| Provider | Category | Use | Citation |
|---|---|---|---|
| **GitHub** | Source Control / VCS | Code hosting, version control, PR/review workflow for this repository — used on the free tier | repo remote (`.git`), this repository itself |
| **GitHub OAuth 2.0** | Auth | "Sign in with GitHub" identity provider (separate from GitHub-as-VCS usage above) | `services/auth-service/app/services/oauth_service.py` |

---

## Open Source (Self-Hosted / Library)

| Provider | Category | Use | Citation |
|---|---|---|---|
| **NVIDIA Triton Inference Server** | AI/ML Serving | Primary model-serving backend for ASR, TTS, NMT, OCR, NER, diarization, etc., resolved per-request via the platform-core-service model registry | `libs/ai4i_core/pyproject.toml` (`tritonclient[http]`), `docs/architecture/00-overview.md`, `services/inference-service/env.template` |
| **vLLM / llama.cpp / Ollama (OpenAI-compatible)** | AI/ML Serving | `inference-service` proxies `/chat/completions` in OpenAI's wire format to a self-hosted LLM backend — protocol compatibility only, not a call to OpenAI's SaaS API | `services/inference-service/services/llm_service.py` (`OpenAIProxyService`), `docs/architecture/03-inference-service.md` |
| **PostgreSQL 15** | Database | Primary relational store; per-service databases via SQLAlchemy async + Alembic | `docker-compose-local.yml`, `infrastructure/databases/migrations/postgres/alembic/` |
| **Redis 7** | Cache / Session | Caching, rate limiting, JWT/API-key revocation, OAuth state, service-resolution cache | `docker-compose-local.yml`, `docs/architecture/00-overview.md` |
| **OpenSearch 2.11 (+ Dashboards)** | Logging/Tracing | Trace and log storage, queried via `platform-core-service` `/telemetry/traces/search` | `docker-compose-local.yml`, `services/platform-core-service/requirements.txt` |
| **Apache Kafka (Confluent `cp-kafka`) + Zookeeper** | Streaming | Telemetry export (OTel spans) and billing/PPU event consumption (`kafka-consumers`) | `docker-compose-local.yml`, `services/kafka-consumers/requirements.txt` |
| **Fluent Bit** | Log Shipping | Ships container logs/spans into OpenSearch | `docker-compose-local.yml`, `infrastructure/fluent-bit/` |
| **Prometheus** | Monitoring | Metrics scraping/storage; `inference-service` exposes `/enterprise/metrics` | `docker-compose-local.yml`, `infrastructure/prometheus/` |
| **Grafana** | Monitoring | Dashboards over Prometheus data | `docker-compose-local.yml`, `infrastructure/grafana/` |
| **Alertmanager** | Monitoring | Alert routing (webhook back to platform-core) | `docker-compose-local.yml`, `infrastructure/alertmanager/` |
| **Node Exporter** | Monitoring | Host-level metrics | `docker-compose-local.yml` |
| **OpenTelemetry SDK/API** | Instrumentation | Tracing/metrics instrumentation library (FastAPI, SQLAlchemy, Redis) | all services' `requirements.txt` |
| **Apache APISIX** | API Gateway | Production/staging API gateway with forward-auth — lives outside this repo | `README.md`, `docs/architecture/00-overview.md` |
| **Nginx** | API Gateway | Local dev reverse-proxy substitute doing forward-auth + CORS | `infrastructure/nginx/nginx.conf` |
| **SonarQube (Community Edition)** | Code Quality | Static analysis / code scanning, self-hosted | `sonar-project.properties`, `sonar-scope-change.md` |

---

## Not Used

The following common categories of third-party provider were checked for and found **not** to be integrated anywhere in the repo:

- **Cloud IaaS SDKs** — no AWS/GCP/Azure SDK (`boto3`, `@aws-sdk/*`, `google-cloud-*`, `azure-*`) dependencies in application code. AWS is used at the infrastructure level (deployments, servers) — see the Paid/Commercial SaaS table above — but no service calls AWS APIs directly through an SDK.
- **Object storage** (S3, MinIO, GCS, Azure Blob) — audio/image payloads are passed as base64 in request bodies and are not persisted to blob storage (`docs/architecture/03-inference-service.md`).
- **Payments** (Stripe, Razorpay, PayPal) — no references found.
- **Direct commercial LLM APIs** (OpenAI, Anthropic, Azure OpenAI, Google Vertex/Gemini, Cohere, Hugging Face Hub) — no SDK or API-key integration found; the platform only speaks the OpenAI wire protocol to self-hosted backends.
- **Hosted CI/CD** — no `.github/workflows` or cloud pipeline config exists in this repo.
- **SendGrid, Mailgun, Postmark, Twilio, Slack, Microsoft OAuth** — env-var placeholders were found in unused stub-service scaffolding, but none are wired into active code.

---

## Open-Source Alternatives to Paid Services

Where a paid provider is in use, the table below lists viable open-source alternatives, for reference if the team wants to reduce vendor lock-in or licensing cost.

| Paid Service | Category | Open-Source Alternative(s) | Notes |
|---|---|---|---|
| **AWS** | Cloud Infrastructure | OpenStack (self-hosted private cloud); bare-metal + Kubernetes (k3s/kubeadm) | Replacing a full IaaS provider is a major undertaking — most teams choose this only if self-hosting on owned hardware. OpenStack offers the closest API-level parity (compute/network/block storage). |
| **Amazon SES** | Transactional Email | Postal, Mailu, Maddy Mail Server, or Postfix + OpenDKIM/OpenDMARC | Since `libs/ai4i_core/ai4i_core/email/providers/smtp.py` is a generic SMTP client, switching requires **no code change** — only pointing `SMTP_HOST`/credentials at the new self-hosted relay and configuring SPF/DKIM/DMARC for deliverability. |

These are suggestions, not adopted decisions — evaluate operational overhead (hosting, patching, uptime ownership) against the cost of the managed offering before migrating any of them.

---
