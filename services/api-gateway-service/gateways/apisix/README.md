# APISIX gateway

Use this folder when `GATEWAY_PROVIDER=apisix` and `COMPOSE_PROFILES=apisix` in the root `.env`. `config.yaml` sets `node_listen: 8080`.

## Environment-agnostic config (local and production)

The same **`apisix.yaml`** is used for local (Docker Compose) and production (e.g. sandbox.ai4inclusion.org). At container start, **`substitute-env.sh`** substitutes these variables from the environment into the config; no route changes are required.

| Variable | Description | Local (Docker) | Production (e.g. sandbox) |
|----------|-------------|----------------|----------------------------|
| **APISIX_PUBLIC_ORIGIN** | CORS `allow_origins` (scheme + host, no path) | `http://localhost:3000` | `https://sandbox.ai4inclusion.org` |
| **APISIX_UPSTREAM_SUFFIX** | Suffix for upstream service hostnames | *(empty → script uses `.` so hostnames get trailing dot and bypass host DNS search domain)* | `.sandbox.svc.cluster.local` |

- **Local:** When `APISIX_UPSTREAM_SUFFIX` is empty or unset, the script defaults to `.` (trailing dot). Upstreams become e.g. `simple-ui.:3000`, `auth-service.:8081`, so the resolver does not append the host search domain (e.g. idc.tarento.com) and Docker DNS returns the correct container IPs.
- **Production:** Set the two variables in the deployment (e.g. Kubernetes env or ConfigMap) so upstreams are e.g. `simple-ui.sandbox.svc.cluster.local:3000`.

Files:

- **`apisix.yaml`** – Template with placeholders `${APISIX_PUBLIC_ORIGIN}`, `${APISIX_UPSTREAM_SUFFIX}`. Mounted as `apisix.yaml.template` in the container; the script writes the resolved **`apisix.yaml`** into the APISIX conf dir before startup.
- **`substitute-env.sh`** – Runs at container start; uses `envsubst` so only these two variables are replaced (other `$` in the YAML, e.g. in regexes, are left unchanged).
- **`config.yaml`** – APISIX standalone config (listen port, data plane, YAML provider). Not templated.
