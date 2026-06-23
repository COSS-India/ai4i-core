# nginx-gateway Removal — Change Record

**Base branch:** `release-2.2` (https://github.com/COSS-India/ai4i-core/tree/release-2.2)

---

## What changed and why

### The core problem

Running the frontend locally required Docker to be running just for `nginx-gateway`. The nginx container at port 8080 did three things the frontend depended on:

1. **Path-based routing** — `/api/v1/auth/*` → auth-service (:8081), inference task paths → inference-service (:8090), everything else → platform-core (:8095)
2. **Forward-auth** — called `GET /auth/validate` and injected `X-User-ID`, `X-Tenant-ID`, `X-Permission-IDs`, `X-User-Plan` headers into every upstream request
3. **Public-path bypass** — login, register, refresh, and similar routes skipped the auth check

### The replacement

A single Next.js API route — `src/pages/api/v1/[...proxy].ts` — now does all three. It is a catch-all route on the same port 3000 the browser is already talking to. The browser sends every `/api/v1/*` request to the Next.js dev server, and the route forwards it to the right backend service — with auth if required — and streams the response back.

nginx-gateway has been **fully removed** from the local-dev setup:
- The `nginx-gateway` service is **deleted** from `docker-compose-local.yml`.
- The nginx config is **deleted** — the entire `infrastructure/nginx/` directory is gone.
- The dev scripts no longer reference it (no `WAIT_NGINX`, no `wait_for_nginx`, no `--profile frontend` nginx arg).
- Port **8080 is no longer used** locally; there is no gateway container anymore.

Clients that previously hit the API at `:8080` (curl, Postman) should now call the backend services directly: auth-service `:8081`, platform-core `:8095`, inference `:8090`.

---

## Architecture change

### Before

```
Browser
  └─→ nginx-gateway :8080 (Docker)
        ├─ path routing
        ├─ forward-auth via /auth/validate
        └─→ auth-service :8081
            platform-core-service :8095
            inference-service :8090
```

### After

```
Browser
  └─→ Next.js dev server :3000 (native)
        └─ src/pages/api/v1/[...proxy].ts
              ├─ path routing
              ├─ forward-auth via /auth/validate
              └─→ auth-service :8081
                  platform-core-service :8095
                  inference-service :8090
```

---

## Files changed

### 1. `frontend/simple-ui/src/pages/api/v1/[...proxy].ts` — NEW

The entire replacement lives here. Key parts:

**Service routing** (`resolveRoute()`):
- `/api/v1/auth/*` → auth-service (`AUTH_SERVICE_URL`, default `:8081`)
- `/api/v1/platform-core/*` → platform-core (`PLATFORM_CORE_SERVICE_URL`, default `:8095`)
- Path segment matches `INFERENCE_TASKS` set (nmt, asr, tts, ner, ocr, chat, etc.) → inference-service (`INFERENCE_SERVICE_URL`, default `:8090`)
- Everything else → platform-core

**Public-path bypass** — `PUBLIC_AUTH_PATH` regex mirrors nginx's `public-auth-routes`. These paths skip the forward-auth call entirely:
```
login | register | refresh | guest | verify-email | resend-verification |
forgot-password | reset-password | set-password | resend-setup-link | validate | oauth
```

**Forward-auth** (`callAuthValidate()`):
- Calls `GET {AUTH_SERVICE}/api/v1/auth/validate` with the browser's `Authorization` header and `X-Original-URI` (the full request line incl. query string, matching nginx's `$request_uri`)
- Reads `x-user-id`, `x-tenant-id`, `x-permission-ids`, `x-user-plan` from the response
- Injects them as headers on the upstream request to the backend service
- Inbound copies of those identity headers are **stripped first** so a client cannot spoof them
- Returns **401** (no/invalid token) or **403** (forbidden) to the browser; if auth-service is unreachable/errored it surfaces a **502** ("auth validation unavailable") rather than masking it as a 401

**Transport — uses the `http-proxy` library** (proven `node-http-proxy`, the same engine webpack-dev-server uses) instead of a hand-rolled forwarder:
- `bodyParser: false` + `proxy.web(req, res, …)` — the raw request body is **streamed** straight to the upstream (no in-memory buffering); large inference uploads no longer sit in the Node heap
- The upstream response is streamed back; hop-by-hop headers are handled by the library
- `proxyTimeout` (default 60s, `PROXY_UPSTREAM_TIMEOUT_MS`) guards against a hung backend; on connect-refused/timeout the browser gets a clean **502**
- A `proxyRes` hook strips the inference service's own `Access-Control-*` headers (mirrors nginx `proxy_hide_header`)
- `externalResolver: true` — http-proxy owns the response lifecycle, so Next.js doesn't warn about a dangling response

> **New dependency:** `http-proxy` (+ `@types/http-proxy`) — run `npm install` in `frontend/simple-ui` after pulling this change.

---

### 2. `frontend/simple-ui/next.config.js` — MODIFIED

**Removed** the entire `rewrites()` function:
```js
// REMOVED — this was proxying /api/v1/* to nginx at :8080
async rewrites() {
  return [{ source: '/api/v1/:path*',
            destination: `${process.env.LOCAL_API_GATEWAY_ORIGIN
                         || 'http://127.0.0.1:8080'}/api/v1/:path*` }];
},
```

**Removed** `LOCAL_API_GATEWAY_ORIGIN` from the CSP `connect-src` origin list.

**Updated** the CSP dev fallback: `localhost:8080` → `localhost:3000`. All browser-side API calls now resolve to the same origin the page is served from.

---

### 3. `frontend/simple-ui/env.template` — MODIFIED

| Variable | Before | After |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8080` | `http://localhost:3000` |
| `LOCAL_API_GATEWAY_ORIGIN` | `http://nginx-gateway:8080` | **removed** |
| `AUTH_SERVICE_URL` | — | `http://localhost:8081` (new) |
| `INFERENCE_SERVICE_URL` | — | `http://localhost:8090` (new) |
| `PLATFORM_CORE_SERVICE_URL` | — | `http://localhost:8095` (new) |

The three new `*_SERVICE_URL` vars are server-side only (no `NEXT_PUBLIC_` prefix). They are read by `[...proxy].ts` at request time and never exposed to the browser.

---

### 4. `docker-compose-local.yml` — MODIFIED

The entire `nginx-gateway:` service definition has been **deleted**. There is no nginx container in the local stack anymore. The associated nginx config — `infrastructure/nginx/nginx.conf`, and the whole `infrastructure/nginx/` directory — has also been **deleted**.

---

### 4b. Dev scripts — MODIFIED

The `scripts/dev/` helpers no longer reference nginx:
- `scripts/dev/lib/profiles.sh` — removed `WAIT_NGINX` and the `--profile frontend` compose argument; the `frontend` profile now just runs simple-ui natively.
- `scripts/dev/lib/health.sh` — removed `wait_for_nginx`.
- `scripts/dev/up` — profile description and banner no longer mention a Gateway / `:8080`.
- `scripts/dev/lib/infra.sh` — comment updated.

---

### 5. `docs/SETUP_GUIDE.md` — MODIFIED

**Windows (WSL) section** — rewritten to remove the nginx-specific warning. The old text said API calls from the Simple UI would fail if nginx-gateway was not reachable from a native Windows terminal. The new text explains that Docker containers and native services just need to share the same WSL2 `localhost` network — there is no nginx dependency.

**Step 4 (Start Infrastructure Services)** — minimal infra is now `postgres` + `redis` only (`docker compose … up -d postgres redis`). The optional full observability stack adds the Kafka/OpenSearch/Prometheus/Grafana services. No nginx option anymore.

**Step 9.1 (Frontend)** — the Next.js API proxy handles all routing and forward-auth directly; nginx is not required.

**Step 10 port table** — the `nginx-gateway` / `:8080` row has been removed.

**Architecture Notes table** — the `nginx-gateway` row has been removed.

**Troubleshooting** — "Frontend cannot reach nginx-gateway (Windows)" replaced with a generic "Frontend API calls fail (Windows)" section that checks the backend services directly.

---

### 6. `docs/END-TO-END-SETUP-GUIDE.md` — MODIFIED

**Architecture diagram** — the `nginx-gateway :8080` layer has been removed. The Simple UI on `:3000` now sits directly above the backend services.

**Part B3 (Start Docker infrastructure)** — `nginx-gateway` removed from the `up` command; minimal infra is `postgres` + `redis`.

**Part D (curl verification)** — the login (`D3`) and translate (`D4`) curls previously hit the gateway at `:8080`. They now call the services directly: auth-service `:8081` for login, inference `:8090` for the NMT call.

**Part E (Frontend) — updated:**
- Step E1 confirms `NEXT_PUBLIC_API_URL=http://localhost:3000` is the correct expected value (not `:8080`) and explains that the Next.js dev server acts as the proxy.
- Removed the "Why nginx-gateway must be running" block — nginx is not required for the frontend. All browser API calls go to the Next.js dev server on port 3000.

**Port reference / restart / troubleshooting** — `nginx-gateway` / `:8080` rows removed; references updated to the direct service ports.

---

## Minimum required infrastructure after this change

```bash
# Frontend dev — postgres and redis only
docker compose -f docker-compose-local.yml up -d postgres redis

# Then start the three services natively and npm run dev
```

nginx-gateway no longer exists in the local-dev setup — postgres and redis are the entire minimum required infrastructure.
