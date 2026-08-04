import type { NextApiRequest, NextApiResponse } from "next";
import type HttpProxy from "http-proxy";

// http-proxy is a CommonJS module (module.exports = …) with `export = Server`
// types. A default ESM import type-checks, but under Next/webpack the runtime
// interop does NOT unwrap it ("createProxyServer is not a function"). Require it
// directly to bypass the interop, and re-apply the types via the cast below.
// eslint-disable-next-line -- http-proxy CJS interop; see comment above
const httpProxy = require("http-proxy") as {
  createProxyServer(options?: HttpProxy.ServerOptions): HttpProxy;
};

const AUTH_SERVICE = process.env.AUTH_SERVICE_URL || "http://localhost:8081";
const INFERENCE_SERVICE =
  process.env.INFERENCE_SERVICE_URL || "http://localhost:8090";
const PLATFORM_CORE_SERVICE =
  process.env.PLATFORM_CORE_SERVICE_URL || "http://localhost:8095";

// PASSTHROUGH mode. When set (e.g. DEV_BACKEND_ORIGIN=https://dev.ai4inclusion.org),
// every /api/v1/* request is relayed verbatim to this origin — a REAL gateway that
// owns auth + routing + identity-header injection itself. The proxy does NOT
// forward-auth or inject identity headers in this mode (the gateway rejects
// client-supplied identity headers). Unset (default) → the local per-service
// routing + forward-auth mode below, for headerless backends running on localhost.
const GATEWAY_ORIGIN = process.env.DEV_BACKEND_ORIGIN || "";

// Upstream response timeout. Inference can be slow, so default high (matches the
// old nginx default). Override with PROXY_UPSTREAM_TIMEOUT_MS.
const UPSTREAM_TIMEOUT_MS = Number(
  process.env.PROXY_UPSTREAM_TIMEOUT_MS || 60_000
);

const INFERENCE_TASKS = new Set([
  "inference",
  "nmt",
  "asr",
  "tts",
  "ner",
  "transliteration",
  "language-detection",
  "audio-lang-detection",
  "speaker-diarization",
  "language-diarization",
  "ocr",
  "chat",
]);

// Mirrors nginx public-auth-routes regex — no token required for these.
const PUBLIC_AUTH_PATH =
  /^\/api\/v1\/auth\/(login|register|refresh|guest|verify-email|resend-verification|forgot-password|reset-password|set-password|resend-setup-link|validate|oauth)(\/|$|\?)/;

// Anonymous try-it paths: no JWT, no forward-auth.
// Covers NMT/LLM inference try-it and the public service-list endpoint.
// Local-dev only: skips forward-auth for anonymous try-it. Production needs an
// APISIX public route + rate-limit rule for /api/v1/llm/try-it (and nmt) —
// the client sessionStorage counter is advisory and easily bypassed.
const TRY_IT_PUBLIC_PATH =
  /^\/api\/v1\/((?:nmt|llm)\/try-it|(?:model-management\/)?services\/try-it-service-list)(\/|$|\?)/;

// Identity headers the gateway/forward-auth owns. We strip any inbound copies
// (so a client cannot spoof them) and re-inject the validated values.
const IDENTITY_HEADERS = [
  "x-user-id",
  "x-tenant-id",
  "x-tenant-name",
  "x-permission-ids",
] as const;

function resolveRoute(path: string): { target: string; requiresAuth: boolean } {
  if (path.startsWith("/api/v1/auth/")) {
    return { target: AUTH_SERVICE, requiresAuth: !PUBLIC_AUTH_PATH.test(path) };
  }
  if (path.startsWith("/api/v1/platform-core/")) {
    // Public by design: this prefix is platform-core's health namespace only
    // (the health_router is mounted at /api/v1/platform-core). Business
    // endpoints live under /api/v1/{services,metering,alerts,…} and fall
    // through to the authenticated catch-all below. Mirrors the old nginx
    // "Public platform-core health route" block (no auth_request).
    return { target: PLATFORM_CORE_SERVICE, requiresAuth: false };
  }
  const isTryItPublic = TRY_IT_PUBLIC_PATH.test(path);
  const segment = path.split("/")[3]; // /api/v1/{segment}/...
  if (segment && INFERENCE_TASKS.has(segment)) {
    return { target: INFERENCE_SERVICE, requiresAuth: !isTryItPublic };
  }
  return { target: PLATFORM_CORE_SERVICE, requiresAuth: !isTryItPublic };
}

interface UserHeaders {
  // Index signature so this is assignable to the proxy's `headers` (Record<string,string>).
  [key: string]: string;
  "X-User-ID": string;
  "X-Tenant-ID": string;
  "X-Tenant-Name": string;
  "X-Permission-IDs": string;
}

type AuthResult =
  | { ok: true; headers: UserHeaders }
  | { ok: false; status: number };

async function callAuthValidate(
  authHeader: string | undefined,
  originalUri: string,
  originalMethod: string
): Promise<AuthResult> {
  const validateUrl = `${AUTH_SERVICE}/api/v1/auth/validate`;
  const reqHeaders: Record<string, string> = {
    "X-Original-URI": originalUri,
    // APISIX sets both X-Original-URI and X-Original-Method on every forward-auth
    // call. The auth service's _validate_anonymous() requires both to be present
    // before it can confirm an endpoint is public — without X-Original-Method it
    // returns (looked_up=False) and raises 401 even for genuinely public routes.
    "X-Original-Method": originalMethod,
  };
  if (authHeader) {
    reqHeaders["Authorization"] = authHeader;
  }

  try {
    const res = await fetch(validateUrl, {
      method: "GET",
      headers: reqHeaders,
      // Don't let a hung auth-service block indefinitely (proxyTimeout only
      // covers the upstream backend hop, not this validation fetch). The catch
      // below maps AbortError — like any error — to { ok: false, status: 502 }.
      signal: AbortSignal.timeout(3_000),
    });
    if (!res.ok) {
      return { ok: false, status: res.status };
    }
    return {
      ok: true,
      headers: {
        "X-User-ID": res.headers.get("x-user-id") ?? "",
        "X-Tenant-ID": res.headers.get("x-tenant-id") ?? "",
        "X-Tenant-Name": res.headers.get("x-tenant-name") ?? "",
        "X-Permission-IDs": res.headers.get("x-permission-ids") ?? "",
      },
    };
  } catch {
    // auth-service unreachable — distinct from a 401/403 auth decision.
    return { ok: false, status: 502 };
  }
}

// Single shared proxy instance. http-proxy streams the raw request body straight
// to the upstream (no buffering) and pipes the response back, and enforces
// `proxyTimeout` on a hung upstream.
const proxy = httpProxy.createProxyServer({
  proxyTimeout: UPSTREAM_TIMEOUT_MS,
  changeOrigin: true,
});

// The inference service emits its own CORS headers. Browser calls now hit the
// Next.js dev server same-origin so CORS is moot, but strip them anyway to mirror
// the old nginx `proxy_hide_header` and avoid leaking stray/`*` ACAO headers.
proxy.on("proxyRes", (proxyRes) => {
  delete proxyRes.headers["access-control-allow-origin"];
  delete proxyRes.headers["access-control-allow-credentials"];
  delete proxyRes.headers["access-control-allow-methods"];
  delete proxyRes.headers["access-control-allow-headers"];
});

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  // LOCAL-DEV ONLY. next.config.js uses `output: 'standalone'`, which bundles
  // every API route into the deployed server — so without this guard, a
  // production client could reach /api/v1/* here and be forwarded straight to
  // AUTH_SERVICE_URL / INFERENCE_SERVICE_URL / PLATFORM_CORE_SERVICE_URL,
  // bypassing APISIX's rate-limiting, TLS, and IP filtering. In production
  // APISIX owns routing; this route must never forward traffic.
  if (process.env.NODE_ENV !== "development") {
    return res.status(404).end();
  }

  // ── Passthrough mode (DEV_BACKEND_ORIGIN set) ───────────────────────────────
  // Relay /api/v1/* untouched to a REAL gateway (e.g. the deployed dev portal),
  // which owns auth + routing + identity injection. We do NOT forward-auth or
  // inject identity headers here — that gateway rejects client-supplied identity
  // headers — so we strip any inbound ones and relay the request (Authorization
  // included) and let the gateway do the work. The browser still talks to the
  // Next dev server same-origin, so there is no CORS. Mirrors the pre-refactor
  // next.config.js rewrite that let a local UI hit a deployed backend.
  if (GATEWAY_ORIGIN) {
    for (const h of IDENTITY_HEADERS) {
      delete req.headers[h];
    }
    const passRemoteIp =
      (req.headers["x-forwarded-for"] as string)?.split(",")[0]?.trim() ||
      req.socket?.remoteAddress ||
      "";
    const passHeaders: Record<string, string> = {};
    if (passRemoteIp) passHeaders["X-Real-IP"] = passRemoteIp;
    proxy.web(req, res, { target: GATEWAY_ORIGIN, headers: passHeaders }, () => {
      if (res.writableEnded) return;
      if (!res.headersSent) {
        res.setHeader("Content-Type", "application/json");
        res.status(502).json({ detail: "Bad gateway" });
      } else {
        res.end();
      }
    });
    return;
  }

  const segments = (req.query.proxy as string[]) ?? [];
  const basePath = "/api/v1/" + segments.join("/");
  // Full original request line (path + query) — faithful to nginx's $request_uri.
  const originalUri = req.url || basePath;

  const { target, requiresAuth } = resolveRoute(basePath);

  // Never trust inbound identity headers — strip them before they reach a backend.
  for (const h of IDENTITY_HEADERS) {
    delete req.headers[h];
  }

  // ── Forward-auth ────────────────────────────────────────────────────────────
  let injectedHeaders: Record<string, string> = {};
  if (requiresAuth) {
    const authResult = await callAuthValidate(
      req.headers["authorization"] as string | undefined,
      originalUri,
      req.method ?? "GET"
    );
    if (!authResult.ok) {
      res.setHeader("Content-Type", "application/json");
      if (authResult.status === 403) {
        return res.status(403).json({ detail: "Forbidden" });
      }
      if (authResult.status === 401) {
        return res.status(401).json({ detail: "Authentication required" });
      }
      // Auth-service errored or was unreachable — surface the real failure
      // instead of masking it as a 401 (avoids "please log in" when the
      // gateway simply can't reach auth-service).
      return res
        .status(authResult.status)
        .json({ detail: "Auth validation failed (auth-service unavailable)" });
    }
    injectedHeaders = authResult.headers;
  }

  const remoteIp =
    (req.headers["x-forwarded-for"] as string)?.split(",")[0]?.trim() ||
    req.socket?.remoteAddress ||
    "";
  if (remoteIp) {
    injectedHeaders["X-Real-IP"] = remoteIp;
  }

  // ── Proxy (streams request + response, hop-by-hop handled by http-proxy) ─────
  proxy.web(req, res, { target, headers: injectedHeaders }, (err) => {
    if (res.writableEnded) return;
    if (!res.headersSent) {
      // Connection refused / timeout / reset all surface as a gateway error.
      res.setHeader("Content-Type", "application/json");
      res.status(502).json({ detail: "Bad gateway" });
    } else {
      res.end();
    }
  });
}

export const config = {
  api: {
    bodyParser: false,
    responseLimit: false,
    // http-proxy owns the response lifecycle; tell Next not to expect us to
    // resolve/return and not to warn about a dangling response.
    externalResolver: true,
  },
};
