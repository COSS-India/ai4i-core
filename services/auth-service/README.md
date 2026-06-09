# auth-service

Authentication & authorization for the **ai4i-core** platform — users, tenants, RBAC,
API keys, and OAuth2. Issues and validates JWTs; the nginx gateway
(`docker-compose-local.yml`'s `nginx-gateway`, config at
`infrastructure/nginx/nginx.conf`) calls `/auth/validate` as an `auth_request`
subrequest on every request and trusts the identity headers it returns
(`X-User-ID`, `X-Tenant-ID`).

| | |
|---|---|
| **Port** | `8081` |
| **Stack** | FastAPI · Python 3.11 |
| **Database** | PostgreSQL `ai4iplatform_auth` |
| **Entrypoint** | `app/main.py` |

## Architecture

Full design, diagrams, and code-anchored detail live in the architecture docs:

- **[docs/architecture/01-auth-service.md](../../docs/architecture/01-auth-service.md)** — this service in depth: AuthN/AuthZ, RBAC, users, tenants, API keys, OAuth2, JWT issuance & gateway validation.
- [docs/architecture/00-overview.md](../../docs/architecture/00-overview.md) — system overview (**start here**).

## Run

Infrastructure (PostgreSQL, Redis, …) runs in Docker via
[`docker-compose-local.yml`](../../docker-compose-local.yml) at the repo root; application
services run natively in development.

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8081
```

Container image: see [`Dockerfile`](./Dockerfile) — `CMD uvicorn app.main:app --host 0.0.0.0 --port 8081 --workers 4`.
