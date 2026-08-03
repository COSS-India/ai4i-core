/**
 * Runtime (server) config for values that must change via ConfigMap without
 * rebuilding the Next.js image.
 *
 * NEXT_PUBLIC_* is inlined into the browser bundle at `next build`, so ConfigMap
 * updates never reach the client. These settings are read from process.env on
 * the Next.js server (or /api/config) and applied before the app renders.
 *
 * Preferred env names (no NEXT_PUBLIC_ prefix). Legacy NEXT_PUBLIC_* names are
 * still accepted so existing ConfigMaps keep working during the migration.
 */

export type RuntimeConfig = {
  /** Browser-facing API origin. Empty ⇒ same-origin (Next.js proxy). */
  apiUrl: string;
  /** Telemetry service origin. Empty ⇒ same-origin proxy paths. */
  telemetryServiceUrl: string;
  /** Comma-separated yaml task-type names (e.g. "llm" or "llm,nmt"). Empty ⇒ full catalog. */
  enabledTaskTypes: string;
};

const EMPTY: RuntimeConfig = {
  apiUrl: "",
  telemetryServiceUrl: "",
  enabledTaskTypes: "",
};

let cached: RuntimeConfig = { ...EMPTY };

function firstEnv(...keys: string[]): string {
  for (const key of keys) {
    const value = process.env[key];
    if (value != null && String(value).trim() !== "") {
      return String(value).trim();
    }
  }
  return "";
}

/** Read config from the Node process env (server / API route only). */
export function getServerRuntimeConfig(): RuntimeConfig {
  return {
    apiUrl: firstEnv("API_URL", "NEXT_PUBLIC_API_URL"),
    telemetryServiceUrl: firstEnv(
      "TELEMETRY_SERVICE_URL",
      "NEXT_PUBLIC_TELEMETRY_SERVICE_URL",
    ),
    enabledTaskTypes: firstEnv(
      "ENABLED_TASK_TYPES",
      "NEXT_PUBLIC_ENABLED_TASK_TYPES",
    ),
  };
}

export function getRuntimeConfig(): RuntimeConfig {
  return cached;
}

export function applyRuntimeConfig(config: RuntimeConfig): void {
  cached = {
    apiUrl: (config.apiUrl ?? "").trim(),
    telemetryServiceUrl: (config.telemetryServiceUrl ?? "").trim(),
    enabledTaskTypes: (config.enabledTaskTypes ?? "").trim(),
  };
  if (typeof window !== "undefined") {
    window.__RUNTIME_CONFIG__ = cached;
  }
}

export function getApiBaseUrl(): string {
  return cached.apiUrl;
}

export function getTelemetryServiceUrl(): string {
  return cached.telemetryServiceUrl;
}

/** Parsed allowlist; empty array ⇒ no filter (full catalog). */
export function getEnabledTaskTypes(): string[] {
  return cached.enabledTaskTypes
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

declare global {
  interface Window {
    __RUNTIME_CONFIG__?: RuntimeConfig;
  }
}
