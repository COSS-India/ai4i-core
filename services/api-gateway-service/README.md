# API Gateway Service (gateway-agnostic config)

This folder holds **gateway-agnostic configuration** for the project. No application code (e.g. no Python)—only YAML for each supported gateway. **Only one gateway runs at a time**; which one is controlled by **`GATEWAY_PROVIDER`** and **`COMPOSE_PROFILES`** in the root **`.env`** (set both to the same value: `apisix` or `kong`).

## Choosing the gateway

Set **`GATEWAY_PROVIDER`** and **`COMPOSE_PROFILES`** in the project root **`.env`** (copy from `env.template` if needed) to the same value: `apisix` or `kong`. Compose starts only that gateway. Leave both unset to run no gateway.

Each microservice that talks to the gateway has **`API_GATEWAY_URL`** in its own **`services/<service-name>/env.template`** (copy to `.env`). Use `http://api-gateway-service:8080` so it works with either APISIX or Kong (both use the same network alias).

Run Docker Compose as usual; no need to pass `--profile` when `COMPOSE_PROFILES` is set in `.env`:

- **APISIX:** set `GATEWAY_PROVIDER=apisix` and `COMPOSE_PROFILES=apisix` in `.env`, then `docker compose -f docker-compose-local.yml up -d`
- **Kong:** set `GATEWAY_PROVIDER=kong` and `COMPOSE_PROFILES=kong` in `.env`, then `docker compose -f docker-compose-local.yml up -d`

## Layout

```
api-gateway-service/
├── README.md                # This file
└── gateways/
    ├── kong/                # Kong declarative config
    │   ├── kong.yml         # Routes, upstreams, services, plugins
    │   ├── substitute-env.sh
    │   └── README.md
    └── apisix/              # APISIX (placeholder)
        ├── apisix.yaml
        └── README.md
```

## Adding another gateway

1. Add a new directory under `gateways/<name>/` with the gateway’s config (e.g. YAML).
2. In the repo’s Docker Compose (`docker-compose.yml` and `docker-compose-local.yml`):
   - Define a service for the new gateway.
   - Put that service behind a profile, e.g. `profiles: ["<name>"]` (use the same value for `GATEWAY_PROVIDER` and `COMPOSE_PROFILES` in `.env`).
3. Document in this README and in root `env.template`: set `GATEWAY_PROVIDER=<name>` and `COMPOSE_PROFILES=<name>` so only that gateway starts.

## Relation to other services

- **api-gateway-legacy** – Old Python API gateway; no longer run from Docker Compose. Use APISIX or Kong (set `GATEWAY_PROVIDER` and `COMPOSE_PROFILES` to `apisix` or `kong` in `.env`) instead.
- **Konga-API-manager** – Kong Manager UI and custom plugins (e.g. token-validator). Plugins are still loaded from there when Kong runs; only the declarative config lives under `gateways/kong/`.
