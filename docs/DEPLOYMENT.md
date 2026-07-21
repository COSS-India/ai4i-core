# Production Deployment Guide

> **Draft.** This guide covers deploying AI4I-Core to a production or production-like
> environment. It complements the local guides ([SETUP_GUIDE](./SETUP_GUIDE.md),
> [END-TO-END-SETUP-GUIDE](./END-TO-END-SETUP-GUIDE.md)). Sections marked **[team input]**
> need environment-specific values from the operations team before this is final.

## Who this guide is for

Platform engineers and DevOps teams deploying AI4I-Core on their own infrastructure, beyond
a local developer machine. It assumes familiarity with Docker, a reverse proxy or API
gateway, PostgreSQL, and Redis.

## Deployment topology

A production deployment has four planes:

1. **Gateway** — a single entry point that does path routing and forward-auth. Every
   external request is authorized at the gateway by calling auth-service
   `/api/v1/auth/validate`, which returns identity headers (`X-User-ID`, `X-Tenant-ID`) that
   downstream services trust.
2. **Application services** — three FastAPI services:

   | Service | Port | Database | Role |
   |---------|------|----------|------|
   | auth-service | 8081 | PostgreSQL `ai4iplatform_auth` | AuthN/AuthZ, users, tenants, RBAC, API keys, OAuth2, JWT |
   | platform-core-service | 8095 | PostgreSQL `ai4iplatform_core` | Model/service registry, alerts, telemetry query, PII policies |
   | inference-service | 8090 | stateless | Inference orchestration over Triton / OpenAI-compatible backends |

3. **Data plane** — PostgreSQL (per-service databases) and Redis (cache, rate-limit and
   session state, resolution cache).
4. **Observability lane** — Kafka transports OpenTelemetry spans, Fluent Bit ships logs and
   traces to OpenSearch, and Prometheus/Grafana/Alertmanager handle metrics and alerting.
   This lane is separate from the business-data path. See
   [TRACING-OBSERVABILITY-LOCAL-SETUP](./TRACING-OBSERVABILITY-LOCAL-SETUP.md) for the local
   equivalent and [architecture/00-overview](./architecture/00-overview.md) for the diagrams.

## Gateway

Production and staging use **APISIX** as the API gateway (external to this repository). It
performs the same path routing and forward-auth pattern used everywhere else in the stack.

This repository includes an **nginx reference gateway** at
[`infrastructure/nginx/nginx.conf`](../infrastructure/nginx/nginx.conf) that demonstrates the
required behavior and can be used as a starting point:

- An internal `= /_auth_validate` subrequest proxies to auth-service
  `/api/v1/auth/validate` (body stripped, `Authorization` and `X-Original-URI` forwarded).
- Public auth routes (`login`, `register`, `refresh`, `guest`, `verify-email`,
  `forgot-password`, `reset-password`, `oauth`, `validate`, and more) bypass token checks.
- All other `/api/v1/*` routes require a valid token and are authorized via the forward-auth
  subrequest before proxying to the upstream service.
- Upstreams are `auth_service` (8081), `platform_core_service` (8095), and
  `inference_service` (8090).

**[team input]** For a real production deployment, replace the localhost CORS origins and
`host.docker.internal` upstreams in `nginx.conf` with your production hostnames, or configure
the equivalent routes and forward-auth in APISIX. Document the exact APISIX route
configuration used in your environment here.

## Prerequisites

- Docker 20.10+ / Docker Compose 2.0+ (or an equivalent container runtime and orchestrator)
- PostgreSQL 15 and Redis 7 (managed services or self-hosted)
- Python 3.11 runtime for the application services
- Node 18+ if you deploy the Simple UI frontend
- One or more model servers reachable from inference-service (NVIDIA Triton and/or an
  OpenAI-compatible LLM backend)
- **[team input]** TLS certificates and DNS for the gateway hostname

## Configuration

1. **Generate environment files.** `./scripts/setup-env.sh` creates the root `.env` and
   per-service `.env` files. For production, review every value; do not ship development
   defaults.
2. **Point services at production data stores.** Set the PostgreSQL and Redis hosts, ports,
   and credentials in each service `.env`. Use the real hostnames, not the Docker-internal
   `postgres`/`redis` names.
3. **Set model-server endpoints.** Configure `TRITON_ENDPOINT_*` (and any LLM backend URL) to
   your production model servers. Services registered with a blank `endpoint` fail inference
   until set; see [SETUP_GUIDE](./SETUP_GUIDE.md), Step 10, for the `PATCH /api/v1/services`
   flow.
4. **Rotate all secrets.** Change the default admin password (`ADMIN_DEFAULT_PASSWORD`), JWT
   signing keys, and any API keys. **[team input]** Record your secret-management approach
   (for example a vault or orchestrator secrets) here.

The full variable list and defaults are in [SETUP_GUIDE](./SETUP_GUIDE.md).

## Database migrations

Run migrations before starting the services, and on every upgrade:

```bash
./scripts/migrate.sh all upgrade
```

Migrations are single-headed (validated by `scripts/validate-migrations.py`). Re-running the
command is also how seed data is applied. See [RELEASE](../RELEASE.md) for the release and
upgrade sequence.

## Running the services

Run the three application services (auth, platform-core, inference) behind the gateway, plus
the data plane and observability stack. The container definitions and infrastructure configs
live under [`infrastructure/`](../infrastructure/):

- `infrastructure/nginx/` — reference gateway
- `infrastructure/databases/` — database adapters, migrations, seeders
- `infrastructure/redis/`, `infrastructure/kafka/` — data plane and span transport
- `infrastructure/prometheus/`, `infrastructure/grafana/`, `infrastructure/alertmanager/` —
  metrics and alerting
- `infrastructure/opensearch/`, `infrastructure/fluent-bit/` — logs and traces

**[team input]** Document your production orchestration (Compose file, Kubernetes manifests,
or other), replica counts, resource limits, and health-check wiring here. Each service
exposes a `/health` endpoint and Prometheus metrics.

## Fork and patch

To customize or patch the platform:

1. Fork `COSS-India/ai4i-core` and branch from the active release branch.
2. Make changes following [CONTRIBUTING](../CONTRIBUTING.md); keep migrations single-headed.
3. Build and deploy from your fork. The shared library `ai4i-core` is published to PyPI; bump
   its version only when the library changes (see [RELEASE](../RELEASE.md)).

## Verify the deployment

- Gateway routes reach each service and reject unauthenticated protected requests.
- `GET /health` on each service returns healthy.
- `GET /api/v1/inference/tasks` lists the registered inference tasks.
- A sample inference call returns output (see [USER_GUIDE](./USER_GUIDE.md) once available,
  or [END-TO-END-SETUP-GUIDE](./END-TO-END-SETUP-GUIDE.md) for a translate example).
- Metrics appear in Grafana and logs/traces in OpenSearch Dashboards.

## Related documentation

- [SETUP_GUIDE](./SETUP_GUIDE.md) · [END-TO-END-SETUP-GUIDE](./END-TO-END-SETUP-GUIDE.md) · [DOCKER-COMPOSE-LOCAL-REFERENCE](./DOCKER-COMPOSE-LOCAL-REFERENCE.md)
- [Architecture overview](./architecture/00-overview.md)
- [TRACING-OBSERVABILITY-LOCAL-SETUP](./TRACING-OBSERVABILITY-LOCAL-SETUP.md)
- [RELEASE](../RELEASE.md)
