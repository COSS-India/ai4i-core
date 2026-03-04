# Kong Gateway

Declarative configuration for [Kong](https://konghq.com/) when used as the project API gateway. Use this folder when `GATEWAY_PROVIDER=kong` and `COMPOSE_PROFILES=kong` in the root `.env`.

## Activation

Ensure the project root `.env` contains:

```bash
GATEWAY_PROVIDER=kong
COMPOSE_PROFILES=kong
```

## Files

| File | Purpose |
|------|--------|
| **`kong.yml`** | Kong declarative config: upstreams, targets, services, routes, and plugins. |
| **`substitute-env.sh`** | Runs before Kong starts to substitute environment variables (e.g. `${ASR_API_KEY}`) into the config. |

## Custom Plugins

Custom plugins (e.g. token-validator) live under `services/Konga-API-manager/plugins/` and are mounted into the Kong container by Docker Compose. Only the declarative gateway config is maintained in this directory.
