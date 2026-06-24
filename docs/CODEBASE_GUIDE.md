# Codebase Guide

> Read this document to understand how the repository is laid out, where to find things,
> and where to start.

---

## Overview

`ai4i-core` is a **multi-tenant AI inference platform** for Indic language tasks (NMT,
ASR, TTS, LLM, NER, OCR, and more). It is structured as three Python microservices, a
Next.js web portal, a shared Python library, and the infrastructure/observability stack
that runs underneath all of them.

```
ai4i-core/
├── services/               ← three FastAPI microservices
├── frontend/               ← Next.js web portal
├── libs/                   ← shared Python library used by all services
├── infrastructure/         ← database migrations and observability configs
├── tests/                  ← cross-service integration and E2E tests
├── scripts/                ← setup and migration helper scripts
├── docs/                   ← architecture docs, setup guide, this file
└── docker-compose-local.yml← one-command local stack
```

The full system architecture and request-flow diagrams live in
[`docs/architecture/00-overview.md`](architecture/00-overview.md). The step-by-step
local environment setup lives in [`docs/SETUP_GUIDE.md`](SETUP_GUIDE.md). Start with
those if you want the big picture before diving into code.

---

## Repository layout at a glance

| Path | What lives there |
|------|-----------------|
| `services/auth-service/` | Authentication, authorisation, multi-tenancy, JWT issuance |
| `services/platform-core-service/` | Model registry, alerts, PII policies, billing |
| `services/inference-service/` | Unified inference endpoint for all AI task types |
| `frontend/simple-ui/` | Next.js 14 web portal (TypeScript, React) |
| `libs/ai4i_core/` | Shared utilities: logging, observability, email, telemetry |
| `infrastructure/databases/` | Alembic migrations for all PostgreSQL schemas |
| `infrastructure/prometheus/` | Prometheus config and alert rules |
| `infrastructure/grafana/` | Grafana dashboard JSON and datasource provisioning |
| `infrastructure/opensearch/` | OpenSearch config and index templates |
| `infrastructure/fluent-bit/` | Fluent Bit log-shipping config |
| `infrastructure/alertmanager/` | Alertmanager notification routing |
| `tests/` | Cross-service integration tests and E2E browser tests |
| `scripts/` | `setup-env.sh`, `migrate.sh`, `validate-migrations.py` |
| `docs/` | Architecture docs, setup guide, images |

---

## Services

### `services/auth-service/`

> **Docstring:** *"Auth-service is the only service that performs JWT verification. It
> issues tokens and verifies them for the `/auth/validate` endpoint. No tracing or
> observability — logging only."*
> — `services/auth-service/app/main.py`

Handles everything authentication- and authorisation-related:

- User registration, login, password reset, email verification
- JWT issuance (RS256) and validation; JWKS endpoint
- API key generation and validation
- Multi-tenancy: tenant lifecycle (create, suspend, activate), tenant plans
- RBAC: roles, permissions, the `/auth/validate` forward-auth endpoint
- OAuth2 provider integration

**Internal layout:**

```
app/
├── core/           ← config, DB session, Redis, JWT verifier, permission checker
├── models/         ← SQLAlchemy ORM models (User, Tenant, Role, ApiKey, …)
├── repositories/   ← data-access layer — one repository class per model
├── services/       ← business logic (auth_service, tenant_service, token_service, …)
├── routes/         ← FastAPI route handlers
├── schemas/        ← Pydantic request/response models
├── dependencies/   ← FastAPI dependency-injection wires (JWT, permissions, rate-limit)
└── utils/          ← helpers (email, username generation)
```

**Key files to read first:**
- `app/main.py` — application factory and startup sequence
- `app/core/config.py` — all environment variables and defaults
- `app/routes/validation.py` — the `/auth/validate` forward-auth endpoint
- `app/services/auth_service.py` — login/signup/token logic

**Database:** `ai4iplatform_auth` (PostgreSQL). Migrations: `infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_auth/`.

---

### `services/platform-core-service/`

> **Docstring:** *"Platform Core Service — FastAPI application factory. No tracing or
> observability — logging only."*
> — `services/platform-core-service/app/main.py`

The control-plane service. Manages configuration and policies that the other services
depend on:

| Domain | What it owns |
|--------|-------------|
| Model management | Registry of ML models and service definitions (URL, task type, parameters) |
| Alert management | Alert rule definitions, execution history, notification receivers, Alertmanager sync |
| PII management | Domain-specific redaction policies, pattern library, audit logs |
| Pay-per-use / billing | Subscription plans, quota configs, usage records, wallet/credit management |
| Telemetry | Proxy query endpoint for OpenSearch trace data (`/telemetry/traces/search`) |

**Internal layout:**

```
app/
├── core/                 ← config, two DB sessions (primary + auth read), Redis
├── models/               ← ORM models, grouped by domain
├── repositories/         ← data access, grouped by domain
├── services/             ← business logic, grouped by domain
│   ├── model-management/ ← model_service.py, service_service.py
│   ├── alert-management/ ← definition, history, receiver, routing, sync services
│   ├── pii-management/   ← detection, redaction, audit, knowledge-base, policy-sync
│   └── pay_per_use/      ← billing policies, quota, rate-limit, wallet
├── routes/               ← FastAPI route handlers
├── schemas/              ← Pydantic models, grouped by domain; shared enums in schemas/enums/
├── utils/                ← OpenSearch client, PromQL builder, endpoint validator, …
└── dependencies/         ← service injection
```

**Key files to read first:**
- `app/main.py` — application factory
- `app/core/config.py` — environment variables; note the two DB connection strings
- `app/routes/model.py` — model registry endpoints
- `app/services/model-management/model_service.py` — model CRUD logic

**Databases:** `ai4iplatform_core` (primary) and a read connection to `ai4iplatform_auth`. Migrations: `infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_core/`.

---

### `services/inference-service/`

> **Docstring:** *"Inference Service - Main entry point. Unified inference endpoint for
> all task services (NMT, ASR, OCR, NER, LLM, etc.)"*
> — `services/inference-service/main.py`

A single `POST /api/v1/inference` endpoint that:

1. Receives a task request (task type + payload)
2. Resolves the target model service URL from platform-core-service
3. Routes to the appropriate task-specific service
4. Forwards the request to the backend (Triton Inference Server or an LLM)
5. Emits an OpenTelemetry trace span (to Kafka → OpenSearch)

**Supported task types:** `nmt`, `asr`, `tts`, `ner`, `ocr`, `transliteration`,
`language_detection`, `audio_lang_detection`, `speaker_diarization`,
`language_diarization`, `llm`.

**Internal layout:**

```
orchestrator/
├── orchestrator.py               ← receives request, calls task service, returns response
└── task_service_registry.py      ← maps task-type string → service class

services/
├── base/                         ← abstract base classes (text, audio, image, config_mapper)
├── nmt_service.py                ← Neural Machine Translation
├── asr_service.py                ← Automatic Speech Recognition
├── tts_service.py                ← Text-to-Speech
├── llm_service.py                ← OpenAI-compatible LLM calls
├── pii_service.py                ← PII detection stub (full logic in platform-core)
└── …                             ← one file per task type

trace/
├── setup.py                      ← OpenTelemetry + Kafka exporter wiring
├── request_span.py               ← span creation per inference request
└── span_attributes.py            ← span attribute constants

routes/
└── inference.py                  ← single POST /api/v1/inference endpoint
```

**Key files to read first:**
- `app_factory.py` — application factory; see how OpenTelemetry is initialised
- `orchestrator/orchestrator.py` — the request-routing logic
- `trace/setup.py` — how spans reach Kafka and then OpenSearch
- `services/base/task_service.py` — interface every task service implements

**Note:** inference-service is the **only** service that emits OpenTelemetry spans and
exposes a Prometheus metrics endpoint (`/enterprise/metrics`).

---

## Shared library — `libs/ai4i_core/`

> **Docstring:** *"ai4i\_core — Consolidated AI4I utility libraries."*
> — `libs/ai4i_core/ai4i_core/__init__.py`

A Python package (`ai4i_core==1.0.1`) installed into every service. Contains all
cross-cutting concerns so each service does not reinvent them.

| Subpackage | Purpose |
|------------|---------|
| `bootstrap/` | FastAPI app-factory helpers: cache, DB, Redis, schemas, API versioning |
| `email/` | Provider-agnostic transactional email client (SMTP and console/debug providers) |
| `exceptions/` | Shared exception hierarchy, `ErrorDetail` response envelope, FastAPI handlers |
| `logging/` | Structured JSON logging, `RequestMiddleware` that injects correlation IDs |
| `observability/` | Prometheus metric definitions and ASGI collection middleware |
| `telemetry/` | OpenTelemetry tracing, W3C context propagation, OpenSearch query clients |

**Key files to read first:**
- `ai4i_core/__init__.py` — package-level docstring lists all subpackages
- `logging/middleware.py` — `RequestMiddleware` (adds correlation IDs to every request)
- `observability/middleware.py` — Prometheus metrics ASGI middleware
- `telemetry/traceability.py` — trace-ID propagation across service boundaries

All services install this library via `pip install -e ../../libs/ai4i_core` (see each
service's `requirements.txt`).

---

## Frontend — `frontend/simple-ui/`

A **Next.js 14** web application (TypeScript, React).

```
src/
├── components/
│   ├── auth/           ← login, register, auth guards
│   ├── nmt/            ← machine translation UI
│   ├── asr/            ← speech recognition UI
│   ├── tts/            ← text-to-speech UI
│   ├── llm/            ← LLM chat completion UI
│   ├── pii/            ← PII management UI
│   ├── observability/  ← trace viewer (reads from platform-core /telemetry endpoint)
│   └── profile/        ← user profile and settings
├── hooks/              ← React hooks that wrap API calls
├── pages/              ← Next.js page routes
├── api/                ← Next.js API routes (thin proxies to backend services)
└── lib/                ← shared utilities
```

**Tooling:** Jest + React Testing Library (`__tests__/`), ESLint, TypeScript strict mode.

---

## Infrastructure

### Databases (`infrastructure/databases/`)

Alembic manages all schema migrations. There are four migration tracks:

| Track | Schema | Owned by |
|-------|--------|---------|
| `ai4iplatform_auth` | Users, tenants, roles, API keys, tokens | auth-service |
| `ai4iplatform_core` | Models, services, alerts, PII policies, billing | platform-core-service |
| `ai4i_platform_db` | Legacy platform configuration | — |
| `alerting_db` / `policy_db` | Alert history, policy storage | — |

Run migrations with `scripts/migrate.sh` or via the `ai4v-migration-runner` Docker
service. See `infrastructure/databases/MIGRATIONS.md` for detailed instructions.

**Layout:**
```
databases/
├── migrations/postgres/alembic/
│   ├── env.py              ← Alembic runner
│   ├── alembic.ini
│   └── versions/           ← one subdirectory per database schema
├── adapters/postgres_adapter.py
├── core/base_adapter.py
└── cli.py                  ← CLI entry point
```

### Observability stack

| Component | Config location | Role |
|-----------|----------------|------|
| Prometheus | `infrastructure/prometheus/` | Metrics scrape + time-series |
| Grafana | `infrastructure/grafana/` | Dashboards (4 JSON dashboards provided) |
| Alertmanager | `infrastructure/alertmanager/` | Alert routing and notification |
| OpenSearch | `infrastructure/opensearch/` | Trace spans + container logs |
| Fluent Bit | `infrastructure/fluent-bit/` | Ships logs and spans to OpenSearch |

Full observability architecture diagram: [`docs/images/observability.mmd`](images/observability.mmd).

---

## Cross-service integration tests — `tests/`

```
tests/
├── e2e/
│   └── test_frontend_integration.py   ← browser automation
└── integration/
    ├── test_authentication_flows.py   ← end-to-end auth flows
    ├── test_api_gateway_routing.py    ← gateway routing behaviour
    ├── test_asr_service.py
    ├── test_nmt_service.py
    ├── test_tts_service.py
    └── test_websocket_streaming.py
```

Each service also has its own unit and integration test suite:

| Service | Test directory |
|---------|---------------|
| auth-service | `services/auth-service/tests/` (20+ files) |
| inference-service | `services/inference-service/test/` (10+ files) |
| platform-core-service | `services/platform-core-service/tests/` |

---

## Scripts — `scripts/`

| Script | Purpose |
|--------|---------|
| `setup-env.sh` | Copies `env.template` to `.env` and prompts for values |
| `migrate.sh` | Runs Alembic migrations against all target databases |
| `run-migration-cli.sh` | Thin wrapper around the migration CLI |
| `validate-migrations.py` | Checks migration files for consistency (used as a pre-commit hook) |

---

## Steps to navigate the code

1. **Understand the system** — read [`docs/architecture/00-overview.md`](architecture/00-overview.md) for the overall architecture and request flow.

2. **Set up your local environment** — follow [`docs/SETUP_GUIDE.md`](SETUP_GUIDE.md) to bring up the full stack with `docker-compose-local.yml`.

3. **Pick the service you are working on** and read its `README.md`:
   - `services/auth-service/README.md`
   - `services/inference-service/README.md`
   - `services/platform-core-service/README.md`

4. **Read the detailed architecture doc** for that service:
   - [`docs/architecture/01-auth-service.md`](architecture/01-auth-service.md)
   - [`docs/architecture/02-platform-core-service.md`](architecture/02-platform-core-service.md)
   - [`docs/architecture/03-inference-service.md`](architecture/03-inference-service.md)

5. **Find the entry point** — every service follows the same startup pattern:
   - `main.py` (or `app/main.py`) — application factory and lifespan context
   - `app/core/config.py` — all configurable settings
   - `app/routes/` — FastAPI route handlers
   - `app/services/` — business logic
   - `app/repositories/` — data access

6. **Shared utilities** — if a function looks like general infrastructure (logging, metrics, email), it is probably in `libs/ai4i_core/`. Check the subpackage docstrings in `libs/ai4i_core/ai4i_core/__init__.py`.

7. **Add a migration** — if your change touches the database schema, follow the instructions in `infrastructure/databases/MIGRATIONS.md`.

8. **Before committing** — run the pre-commit hooks (`pre-commit run --all-files`) and ensure per-service tests pass.

---

## Further reading

| Document | What it covers |
|----------|---------------|
| [`docs/architecture/00-overview.md`](architecture/00-overview.md) | System diagram, request-flow sequence, infrastructure inventory, licence audit |
| [`docs/architecture/01-auth-service.md`](architecture/01-auth-service.md) | Auth service deep-dive: JWT, RBAC, multi-tenancy, data privacy |
| [`docs/architecture/02-platform-core-service.md`](architecture/02-platform-core-service.md) | Model registry, alerting, PII, billing |
| [`docs/architecture/03-inference-service.md`](architecture/03-inference-service.md) | Inference orchestration, task services, OpenTelemetry tracing |
| [`docs/SETUP_GUIDE.md`](SETUP_GUIDE.md) | Step-by-step local development setup |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | Contribution workflow, branching strategy, PR checklist |
