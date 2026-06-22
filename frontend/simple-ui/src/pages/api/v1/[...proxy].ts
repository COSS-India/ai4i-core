import type { NextApiRequest, NextApiResponse } from "next";
import http from "http";
import https from "https";
import { IncomingMessage } from "http";

const AUTH_SERVICE = process.env.AUTH_SERVICE_URL || "http://localhost:8081";
const INFERENCE_SERVICE =
  process.env.INFERENCE_SERVICE_URL || "http://localhost:8090";
const PLATFORM_CORE_SERVICE =
  process.env.PLATFORM_CORE_SERVICE_URL || "http://localhost:8095";

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

function resolveRoute(path: string): { target: string; requiresAuth: boolean } {
  if (path.startsWith("/api/v1/auth/")) {
    return { target: AUTH_SERVICE, requiresAuth: !PUBLIC_AUTH_PATH.test(path) };
  }
  if (path.startsWith("/api/v1/platform-core/")) {
    return { target: PLATFORM_CORE_SERVICE, requiresAuth: false };
  }
  const segment = path.split("/")[3]; // /api/v1/{segment}/...
  if (segment && INFERENCE_TASKS.has(segment)) {
    return { target: INFERENCE_SERVICE, requiresAuth: true };
  }
  return { target: PLATFORM_CORE_SERVICE, requiresAuth: true };
}

interface UserHeaders {
  "X-User-ID": string;
  "X-Tenant-ID": string;
  "X-Permission-IDs": string;
  "X-User-Plan": string;
}

async function callAuthValidate(
  authHeader: string | undefined,
  originalUri: string
): Promise<{ ok: true; headers: UserHeaders } | { ok: false; status: number }> {
  const validateUrl = `${AUTH_SERVICE}/api/v1/auth/validate`;
  const reqHeaders: Record<string, string> = {
    "X-Original-URI": originalUri,
  };
  if (authHeader) {
    reqHeaders["Authorization"] = authHeader;
  }

  try {
    const res = await fetch(validateUrl, {
      method: "GET",
      headers: reqHeaders,
    });

    if (!res.ok) {
      return { ok: false, status: res.status };
    }

    return {
      ok: true,
      headers: {
        "X-User-ID": res.headers.get("x-user-id") ?? "",
        "X-Tenant-ID": res.headers.get("x-tenant-id") ?? "",
        "X-Permission-IDs": res.headers.get("x-permission-ids") ?? "",
        "X-User-Plan": res.headers.get("x-user-plan") ?? "",
      },
    };
  } catch {
    return { ok: false, status: 502 };
  }
}

// Headers that must not be forwarded to the upstream or back to the client.
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
]);

function proxyRequest(
  method: string,
  targetUrl: string,
  headers: Record<string, string | string[]>,
  body: Buffer | null
): Promise<IncomingMessage> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(targetUrl);
    const lib = parsed.protocol === "https:" ? https : http;
    const options: http.RequestOptions = {
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname + parsed.search,
      method,
      headers,
    };
    const req = lib.request(options, resolve);
    req.on("error", reject);
    if (body && body.length > 0) {
      req.write(body);
    }
    req.end();
  });
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  const segments = (req.query.proxy as string[]) ?? [];
  const basePath = "/api/v1/" + segments.join("/");
  const queryString = req.url?.includes("?")
    ? req.url.slice(req.url.indexOf("?"))
    : "";
  const fullPath = basePath + queryString;

  const { target, requiresAuth } = resolveRoute(basePath);

  // ── Forward-auth ────────────────────────────────────────────────────────────
  let injectedHeaders: UserHeaders | null = null;
  if (requiresAuth) {
    const authResult = await callAuthValidate(
      req.headers["authorization"] as string | undefined,
      basePath
    );
    if (!authResult.ok) {
      const status = authResult.status === 403 ? 403 : 401;
      const detail =
        status === 403 ? "Forbidden" : "Authentication required";
      res.setHeader("Content-Type", "application/json");
      return res.status(status).json({ detail });
    }
    injectedHeaders = authResult.headers;
  }

  // ── Build upstream headers ───────────────────────────────────────────────────
  const upstreamHeaders: Record<string, string | string[]> = {};
  for (const [key, value] of Object.entries(req.headers)) {
    if (key === "host") continue;
    if (HOP_BY_HOP.has(key.toLowerCase())) continue;
    if (value !== undefined) {
      upstreamHeaders[key] = value as string | string[];
    }
  }

  // Inject forwarded-auth identity headers.
  if (injectedHeaders) {
    Object.assign(upstreamHeaders, injectedHeaders);
  }

  const remoteIp =
    (req.headers["x-forwarded-for"] as string)?.split(",")[0]?.trim() ||
    req.socket?.remoteAddress ||
    "";
  if (remoteIp) {
    upstreamHeaders["X-Real-IP"] = remoteIp;
  }

  // ── Collect raw body (bodyParser is disabled) ───────────────────────────────
  const body = await new Promise<Buffer>((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });

  // Keep Content-Length accurate if body was read.
  if (body.length > 0) {
    upstreamHeaders["content-length"] = String(body.length);
  } else {
    delete upstreamHeaders["content-length"];
  }

  // ── Proxy to upstream ────────────────────────────────────────────────────────
  let upstream: IncomingMessage;
  try {
    upstream = await proxyRequest(
      req.method ?? "GET",
      target + fullPath,
      upstreamHeaders,
      body.length > 0 ? body : null
    );
  } catch {
    res.setHeader("Content-Type", "application/json");
    return res.status(502).json({ detail: "Bad gateway" });
  }

  // ── Stream response back ─────────────────────────────────────────────────────
  res.status(upstream.statusCode ?? 200);
  for (const [key, value] of Object.entries(upstream.headers)) {
    if (HOP_BY_HOP.has(key.toLowerCase())) continue;
    if (value !== undefined) {
      res.setHeader(key, value);
    }
  }

  upstream.pipe(res);
}

export const config = {
  api: {
    bodyParser: false,
    responseLimit: false,
  },
};
