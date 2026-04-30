# API Gateway Service

Gateway-agnostic configuration for the AI4I platform. This service holds **no application code**—only declarative YAML and scripts for supported gateways. **Exactly one gateway runs at a time**; selection is controlled by environment variables in the project root.

## Overview

- **Supported gateways:** Apache APISIX, Kong  
- **Configuration:** Declarative routes, upstreams, and plugins per gateway under `gateways/<name>/`  
- **Activation:** Set `GATEWAY_PROVIDER` and `COMPOSE_PROFILES` in the root `.env` (see [Configuration](#configuration))

## Prerequisites

- Docker and Docker Compose
- Root `.env` (copy from `env.template` at project root if needed)

## Configuration

In the **project root** `.env`:

| Variable | Description | Values |
|----------|-------------|--------|
| `GATEWAY_PROVIDER` | Gateway implementation to use | `apisix` or `kong` |
| `COMPOSE_PROFILES` | Compose profile that starts the gateway | Must match `GATEWAY_PROVIDER` (e.g. `apisix` or `kong`) |

Set both to the **same** value. Leave both unset to run **no** gateway.

**Microservices** that call the gateway should set `API_GATEWAY_URL` in their own `services/<service-name>/env.template` (or `.env`). Use:

```bash
API_GATEWAY_URL=http://api-gateway-service:8080
```

This works for both APISIX and Kong (same network alias).

## Quick Start

1. Copy `env.template` to `.env` at the project root (if not already done).
2. Set gateway selection in `.env`:
   - **APISIX:** `GATEWAY_PROVIDER=apisix` and `COMPOSE_PROFILES=apisix`
   - **Kong:** `GATEWAY_PROVIDER=kong` and `COMPOSE_PROFILES=kong`
3. Start the stack (no need to pass `--profile` when `COMPOSE_PROFILES` is set in `.env`):

   ```bash
   docker compose -f docker-compose-local.yml up -d
   ```

## Project Structure

```
api-gateway-service/
├── README.md                 # This file
└── gateways/
    ├── apisix/               # Apache APISIX declarative config
    │   ├── apisix.yaml       # Routes, upstreams (template)
    │   ├── config.yaml       # APISIX standalone config
    │   ├── substitute-env.sh # Env substitution at container start
    │   └── README.md
    └── kong/                 # Kong declarative config
        ├── kong.yml          # Routes, upstreams, services, plugins
        ├── substitute-env.sh # Env substitution before Kong start
        └── README.md
```

## Adding a New Gateway

1. Create `gateways/<name>/` with the gateway’s config (e.g. YAML) and any startup scripts.
2. In the repo’s Compose files (`docker-compose.yml` and `docker-compose-local.yml`):
   - Add a service for the new gateway.
   - Attach it to a profile: `profiles: ["<name>"]` (use the same `<name>` as `GATEWAY_PROVIDER` and `COMPOSE_PROFILES`).
3. Document in this README and in the root `env.template`: set `GATEWAY_PROVIDER=<name>` and `COMPOSE_PROFILES=<name>` to run only that gateway.
