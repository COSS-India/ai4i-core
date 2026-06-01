# ai4i-core — Architecture Documentation

These docs describe the architecture of the **ai4i-core** platform as it actually
works in the current codebase (not an aspirational design). Every non-obvious claim is
anchored to a source path so you can jump straight to the code.

## How to read these docs

| Doc | What it covers |
|-----|----------------|
| [docs/architecture/00-overview.md](./docs/architecture/00-overview.md) | The whole system: Portal → microservices → Kafka → databases, infrastructure inventory, the request path vs the telemetry path. **Start here.** |
| [docs/architecture/01-auth-service.md](./docs/architecture/01-auth-service.md) | Authentication, authorization (RBAC), users, tenants, API keys, OAuth2, JWT issuance & gateway validation. |
| [docs/architecture/02-platform-core-service.md](./docs/architecture/02-platform-core-service.md) | Model/service registry, alert management, telemetry query. |
| [docs/architecture/03-inference-service.md](./docs/architecture/03-inference-service.md) | Unified multi-task inference orchestration (NMT, ASR, TTS, NER, OCR, LLM, …) over Triton/LLM backends. |

> **Diagrams** are written in [Mermaid](https://mermaid.js.org/) and render automatically
> in the GitHub web UI. If you view these files in an editor that doesn't render Mermaid,
> paste the code block into <https://mermaid.live> to see the diagram.

## The services at a glance

| Service | Port | Stack | Primary database | Purpose |
|---------|------|-------|------------------|---------|
| **auth-service** | `8081` | FastAPI / Python 3.11 | PostgreSQL `ai4iplatform_auth` | AuthN/AuthZ, users, tenants, RBAC, API keys, OAuth2; issues & validates JWTs |
| **platform-core-service** | `8095` (host `8102`) | FastAPI / Python 3.11 | PostgreSQL `ai4iplatform_core` | Model & service registry, alerts, telemetry query |
| **inference-service** | `8090` (runs natively on host) | FastAPI / Python 3.11 | stateless | Unified inference orchestration over Triton / OpenAI-compatible LLM backends |

> **Convention:** infrastructure (PostgreSQL, Redis, Kafka, OpenSearch, Prometheus, …)
> runs in Docker via `docker-compose-local.yml`. Application services run natively on
> `localhost` during development; `inference-service` in particular is not a compose
> container and is reached by other containers via `inference-service:host-gateway`.

## Shared library

All three services depend on the in-repo Python library
[`libs/ai4icore_core`](./libs/ai4icore_core/), which provides: structured
`logging` + request middleware, `observability` (OpenTelemetry + Prometheus ASGI),
`telemetry`, `bootstrap` (API `versioning`, async `database` engine/session),
`email` client, shared `exceptions`, and request-scoped `context`.
