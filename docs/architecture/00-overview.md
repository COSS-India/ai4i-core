# Overall Architecture

`ai4i-core` is a multi-tenant AI inference platform. A web **Portal** talks to a set of
**FastAPI microservices** through an **APISIX** gateway; the services persist business data in
**PostgreSQL** and use **Redis** for caching and rate-limit/session state. Observability
data (trace spans, logs, metrics) flows out on a separate lane through **Kafka**,
**Fluent Bit**, **OpenSearch**, **Prometheus**, and **Grafana**.

> ### Where Kafka actually sits
> The mental model is *Portal → Microservice → Kafka → Database*. In the real code,
> **Kafka is on the telemetry path, not the business-data path.** Business writes go
> straight to PostgreSQL. Kafka carries **OpenTelemetry trace spans** emitted by the
> `inference-service` to topic `kafka-topic-otel-trace`
> (`services/inference-service/trace/setup.py:17`), which Fluent Bit forwards to the
> OpenSearch `traces-*` index. The diagrams below keep these two lanes visually separate
> so the distinction is explicit.

## System diagram

```mermaid
flowchart TB
    Portal["Portal — simple-ui<br/>Next.js · :3000"]

    subgraph Edge["Edge"]
        GW["APISIX Gateway<br/>(JWT / API-key check via auth /auth/validate)"]
    end

    subgraph Services["Application services (FastAPI)"]
        AUTH["auth-service<br/>:8081"]
        CORE["platform-core-service<br/>:8095"]
        INF["inference-service<br/>:8090"]
    end

    subgraph Backends["Inference backends"]
        TRITON["Triton Inference Server"]
        LLM["OpenAI-compatible LLM<br/>(vLLM / llama.cpp / …)"]
    end

    subgraph Data["Business data / state"]
        PG[("PostgreSQL 15<br/>ai4iplatform_auth · ai4iplatform_core")]
        REDIS[("Redis 7<br/>token cache, rate limits, OAuth state, resolution cache")]
    end

    subgraph Telemetry["Observability lane"]
        KAFKA["Kafka<br/>topic: kafka-topic-otel-trace"]
        FB["Fluent Bit"]
        OS[("OpenSearch<br/>traces-* · logs")]
        PROM["Prometheus"]
        GRAF["Grafana"]
        AM["Alertmanager"]
    end

    Portal --> GW
    GW --> AUTH
    GW --> CORE
    GW --> INF

    AUTH --> PG
    AUTH --> REDIS
    CORE --> PG
    CORE --> REDIS

    INF -- "resolve serviceId → model + endpoint" --> CORE
    INF --> TRITON
    INF --> LLM

    INF -. "OTEL spans" .-> KAFKA
    KAFKA -.-> FB
    FB -.-> OS
    Services -. "container logs" .-> FB
    Services -. "/metrics scrape" .-> PROM
    PROM --> GRAF
    PROM --> AM
    CORE -- "trace search" --> OS
    AM -- "alert webhook" --> CORE
```

## Request path (sequence)

Every external request is authenticated/authorized at the gateway by calling the
auth-service `/auth/validate` endpoint, which returns identity headers the downstream
service trusts.

```mermaid
sequenceDiagram
    participant P as Portal
    participant GW as APISIX Gateway
    participant A as auth-service
    participant S as platform-core / inference
    participant DB as PostgreSQL

    P->>GW: Request + Bearer JWT or API key
    GW->>A: GET /auth/validate (forward-auth)
    A->>A: Verify JWT (RS256) / API key + resolve RBAC permission
    A-->>GW: 200 + X-User-ID, X-Tenant-ID
    GW->>S: Forward request + X-User-ID / X-Tenant-ID
    S->>DB: Read / write (tenant-scoped)
    DB-->>S: Rows
    S-->>GW: Response
    GW-->>P: Response
```

Permission enforcement is centralized: auth-service loads `api_permissions.json`
(`METHOD:PATH → permission_id`) and the gateway calls `/auth/validate` on every request.
Downstream services do **not** re-check permissions in-process
(`services/auth-service/app/routes/__init__.py`).

> The gateway is **APISIX** in production (the code refers to it as APISIX / nginx
> forward-auth — `services/auth-service/app/routes/validation.py`). It is **external to
> this repository**: not a container in `docker-compose-local.yml`. `/auth/validate` is
> invoked as a forward-auth subrequest (`GET`), and auth-service returns `X-User-ID` /
> `X-Tenant-ID` headers that the gateway injects into the upstream request.

## Infrastructure inventory

Defined in [`docker-compose-local.yml`](../../docker-compose-local.yml). Network:
`microservices-network` (bridge, `172.30.0.0/16`).

| Component | Container | Host port | Role |
|-----------|-----------|-----------|------|
| PostgreSQL 15 | `ai4v-postgres` | 5432 | Primary relational store (SCRAM-SHA-256) |
| Redis 7 | `ai4v-redis` | 6379 | Cache, rate-limit state, OAuth state, resolution cache |
| Zookeeper | `ai4v-zookeeper` | 2181 | Kafka coordination |
| Kafka | `ai4v-kafka` | 9093 (`9093:9092`) | OTEL span transport (telemetry lane). Apps connect via `KAFKA_SERVER` — `localhost:9094` in the local env |
| Prometheus | `ai4v-prometheus` | 9090 | Metrics scrape + time-series store |
| Grafana | `ai4v-grafana` | 3001 | Dashboards |
| Alertmanager | `ai4v-alertmanager` | 9095 | Alert routing / notifications |
| Node Exporter | `ai4v-node-exporter` | 9100 | Host metrics |
| OpenSearch | `ai4v-opensearch` | 9204 | Trace (`traces-*`) + log storage |
| OpenSearch Dashboards | `ai4v-opensearch-dashboards` | 5602 | Trace/log visualization |
| Fluent Bit | `ai4v-fluent-bit` | — | Log/span shipper → OpenSearch |
| migration-runner | `ai4v-migration-runner` | — | On-demand Alembic migrations |
| Portal (simple-ui) | `ai4v-simple-ui` | 3000 | Next.js web UI |

Application services (`auth-service`, `platform-core-service`) are also defined in compose
for convenience; `inference-service` runs natively and is reached via
`inference-service:host-gateway`.

## Databases

| Database | Owner service | Stores |
|----------|---------------|--------|
| `ai4iplatform_auth` | auth-service | users, credentials, tenants, tenant_plans, roles, permissions, API keys, refresh & verification tokens |
| `ai4iplatform_core` | platform-core-service | models, services, alert definitions/history |

**Redis** holds: JWT/API-key validation cache & revocation, per-email reset rate limits,
OAuth state & exchange codes (auth-service); model/service resolution cache (platform-core);
service-resolution cache (inference-service).

**OpenSearch** holds: `traces-*` (OTEL spans from inference-service) and container logs.
platform-core-service queries `traces-*` via its `/telemetry/traces/search` endpoint.

## A note on observability scope

Only **inference-service** wires up OpenTelemetry tracing and the Kafka span exporter
(`services/inference-service/app_factory.py` → `trace/setup.py`). The auth-service and
platform-core-service are explicitly **logging-only** — see the module docstrings in
`services/auth-service/app/main.py` and `services/platform-core-service/app/main.py`
("No tracing or observability — logging only"). All three still emit structured logs
(via `ai4icore_core.logging`) that Fluent Bit ships to OpenSearch, and platform-core
exposes Prometheus metrics.

Distributed traces are stored in and queried from the **OpenSearch `traces-*` index**:
`inference-service/trace/setup.py` installs a `LoggerSpanExporter` →
logs + Kafka (`kafka-topic-otel-trace`) → Fluent Bit → OpenSearch `traces-*`. Trace reads
go through `platform-core` `/telemetry/traces/search` and the frontend
`observabilityService.ts`, both of which query OpenSearch.
