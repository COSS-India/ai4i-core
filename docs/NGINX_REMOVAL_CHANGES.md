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

nginx-gateway is **not deleted**. It remains in `docker-compose-local.yml` for:
- Non-Next.js clients (curl, Postman) that need to hit the API directly at port 8080
- Production-parity testing of the nginx forward-auth flow

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
- Calls `GET {AUTH_SERVICE}/api/v1/auth/validate` with the browser's `Authorization` header and `X-Original-URI`
- Reads `x-user-id`, `x-tenant-id`, `x-permission-ids`, `x-user-plan` from the response
- Injects them as headers on the upstream request to the backend service
- Returns 401 or 403 to the browser if validation fails

**Body and response handling**:
- `bodyParser: false` — disables Next.js body parsing so file uploads and streaming payloads pass through untouched
- Hop-by-hop headers (`connection`, `keep-alive`, `transfer-encoding`, `upgrade`, etc.) stripped in both directions
- `upstream.pipe(res)` — streams the upstream response directly to the client

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

Added a comment block above the `nginx-gateway:` service definition:

```yaml
# Not required for frontend dev — Next.js src/pages/api/v1/[...proxy].ts
# replaces it (handles routing, forward-auth, and header injection).
# Only needed for non-Next.js clients or production-parity testing.
nginx-gateway:
  ...
```

No structural changes to the service itself.

---

### 5. `docs/SETUP_GUIDE.md` — MODIFIED

**Windows (WSL) section** — rewritten to remove the nginx-specific warning. The old text said API calls from the Simple UI would fail if nginx-gateway was not reachable from a native Windows terminal. The new text explains that Docker containers and native services just need to share the same WSL2 `localhost` network — there is no nginx dependency.

**Step 4 (Start Infrastructure Services)** — restructured from 2 options to 3:

- **Option A (new name):** Minimal without nginx — `docker compose … up -d postgres redis` — recommended for frontend development
- **Option B (new):** With nginx-gateway — `docker compose … up -d postgres redis nginx-gateway` — for non-Next.js API clients or production-parity testing. Includes a note that nginx is not required for the Simple UI.
- **Option C (was Option B):** Full observability stack — unchanged, with an addendum showing how to include `nginx-gateway` if wanted

**Step 9.1 (Frontend)** — removed the note that said "nginx-gateway must be running before the frontend can reach the API." New text: the Next.js API proxy handles all routing and forward-auth directly; nginx is not required. Added a note that if Option B was started, the API is also reachable at `:8080` for curl testing.

**Step 10 port table** — `nginx-gateway` row restored but marked `(optional)` with a note it is only present if started with Option B.

**Architecture Notes table** — `nginx-gateway` row restored with `(optional)` label and its own restart command.

**Troubleshooting** — "Frontend cannot reach nginx-gateway (Windows)" section replaced with a generic "Frontend API calls fail (Windows)" section. The nginx-specific curl check is now a conditional addendum rather than the main fix.

---

### 6. `docs/END-TO-END-SETUP-GUIDE.md` — MODIFIED (partial)

**Part E (Frontend) — updated:**
- Step E1 now confirms `NEXT_PUBLIC_API_URL=http://localhost:3000` is the correct expected value (not `:8080`) and explains that the Next.js dev server acts as the proxy.
- Added a prominent note: "`nginx-gateway` is not required for the frontend. All browser API calls go to the Next.js dev server on port 3000."

**Parts A–D and the architecture diagram** retain the original nginx-gateway references because this guide covers the full end-to-end path including curl-based verification via nginx. These sections are intentionally left unchanged as nginx is still valid for those steps.

---

## Minimum required infrastructure after this change

```bash
# Frontend dev — postgres and redis only
docker compose -f docker-compose-local.yml up -d postgres redis

# Then start the three services natively and npm run dev
```

nginx-gateway is no longer in the minimum required set.
