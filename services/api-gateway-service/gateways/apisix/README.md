# Apache APISIX Gateway

Declarative configuration for [Apache APISIX](https://apisix.apache.org/) when used as the project API gateway. Use this folder when `GATEWAY_PROVIDER=apisix` and `COMPOSE_PROFILES=apisix` in the root `.env`.

## Activation

Ensure the project root `.env` contains:

```bash
GATEWAY_PROVIDER=apisix
COMPOSE_PROFILES=apisix
```

APISIX listens on port **8080** (see `config.yaml`: `node_listen: 8080`).

## Environment-Agnostic Configuration

The same **`apisix.yaml`** is used for local (Docker Compose) and production (e.g. sandbox). At container start, **`substitute-env.sh`** substitutes the variables below into the config via `envsubst`; only these placeholders are replaced—other `$` in the YAML (e.g. in regexes) are left unchanged.

### Environment Variables

| Variable | Description | Local (Docker) | Production (e.g. Kubernetes) |
|----------|-------------|----------------|-------------------------------|
| `APISIX_PUBLIC_ORIGIN` | CORS `allow_origins` (scheme + host, no path) | `http://localhost:3000` | `https://sandbox.ai4inclusion.org` |
| `APISIX_UPSTREAM_SUFFIX` | Suffix for upstream service hostnames | Empty (script uses `.` for trailing dot) | e.g. `.sandbox.svc.cluster.local` |

- **Local:** When `APISIX_UPSTREAM_SUFFIX` is empty or unset, the script defaults to `.` (trailing dot). Upstreams become e.g. `simple-ui.:3000`, `auth-service.:8081`, so the resolver does not append the host search domain and Docker DNS resolves to the correct container IPs.
- **Production:** Set both variables in the deployment (e.g. Kubernetes env or ConfigMap) so upstreams are e.g. `simple-ui.sandbox.svc.cluster.local:3000`.

## Tenant-aware metrics (Authorization header)

When requests go through APISIX (not the legacy API gateway), upstream services (e.g. NMT, ASR, TTS) need the client’s **Authorization** header to extract `tenant_id` from the JWT for observability metrics. APISIX forwards all client request headers by default. For routes that use `proxy-rewrite`, we use **`headers.add`** (e.g. `X-Gateway: apisix`) so we only add headers and never overwrite or remove `Authorization`. If you add new routes or change proxy-rewrite to `headers.set`, ensure you do not overwrite or remove the `Authorization` header so tenant metrics stay correct.

## Files

| File | Purpose |
|------|--------|
| **`apisix.yaml`** | Route/upstream template with placeholders `${APISIX_PUBLIC_ORIGIN}`, `${APISIX_UPSTREAM_SUFFIX}`. Mounted as `apisix.yaml.template` in the container; the startup script writes the resolved file into the APISIX conf dir. |
| **`substitute-env.sh`** | Runs at container start; uses `envsubst` to replace only the two variables above. |
| **`config.yaml`** | APISIX standalone config (listen port, data plane, YAML provider). Not templated. |
