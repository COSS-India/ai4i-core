# Kong gateway

Declarative config and entrypoint script for Kong. Used when `GATEWAY_PROVIDER=kong` and `COMPOSE_PROFILES=kong` in the root `.env`.

- **kong.yml** – Kong declarative config (upstreams, targets, services, routes, plugins).
- **substitute-env.sh** – Runs before Kong start to substitute env vars (e.g. `${ASR_API_KEY}`) into the config.

Custom plugins (e.g. token-validator) remain under `services/Konga-API-manager/plugins/` and are mounted into the Kong container by Docker Compose.
