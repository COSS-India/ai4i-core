# platform-core-service

Platform control plane for **ai4i-core** — the model & service registry, alert
management, and the telemetry (trace) query API. Inference requests resolve their
`serviceId` here; trace reads go through `/telemetry/traces/search` (backed by the
OpenSearch `traces-*` index).

| | |
|---|---|
| **Port** | `8095` (host `8102`) |
| **Stack** | FastAPI · Python 3.11 |
| **Database** | PostgreSQL `ai4iplatform_core` |
| **Entrypoint** | `app/main.py` |

## Architecture

Full design, diagrams, and code-anchored detail live in the architecture docs:

- **[docs/architecture/02-platform-core-service.md](../../docs/architecture/02-platform-core-service.md)** — this service in depth: model/service registry, alerts, telemetry query.
- [docs/architecture/00-overview.md](../../docs/architecture/00-overview.md) — system overview (**start here**).

## Run

Infrastructure (PostgreSQL, Redis, OpenSearch, …) runs in Docker via
[`docker-compose-local.yml`](../../docker-compose-local.yml) at the repo root; application
services run natively in development.

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8095
```

Container image: see [`Dockerfile`](./Dockerfile) — `CMD uvicorn app.main:app --host 0.0.0.0 --port 8095 --workers 4`.
