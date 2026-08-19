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

/** Default product display name (AI4IDS-2809). Override with PLATFORM_NAME. */
export const DEFAULT_PLATFORM_NAME = "AI Switch";

/** Default instance logo. Override with ADOPTER_LOGO_URL (http(s) or same-origin path). */
export const DEFAULT_ADOPTER_LOGO_SRC = "/AI4Inclusion_Logo.svg";

export type RuntimeConfig = {
  /** Browser-facing API origin. Empty ⇒ same-origin (Next.js proxy). */
  apiUrl: string;
  /** Telemetry service origin. Empty ⇒ same-origin proxy paths. */
  telemetryServiceUrl: string;
  /** Comma-separated yaml task-type names (e.g. "llm" or "llm,nmt"). Empty ⇒ full catalog. */
  enabledTaskTypes: string;
  /** Product/brand name shown in UI titles, consent, headers. */
  platformName: string;
  /** ConfigMap `ADOPTER_LOGO_URL`; empty ⇒ default SVG. */
  adopterLogoUrl: string;
};

export const EMPTY_RUNTIME_CONFIG: RuntimeConfig = {
  apiUrl: "",
  telemetryServiceUrl: "",
  enabledTaskTypes: "",
  platformName: DEFAULT_PLATFORM_NAME,
  adopterLogoUrl: "",
};

let cached: RuntimeConfig = { ...EMPTY_RUNTIME_CONFIG };

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
    platformName:
      firstEnv("PLATFORM_NAME", "NEXT_PUBLIC_PLATFORM_NAME") ||
      DEFAULT_PLATFORM_NAME,
    adopterLogoUrl: firstEnv("ADOPTER_LOGO_URL", "NEXT_PUBLIC_ADOPTER_LOGO_URL"),
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
    platformName:
      (config.platformName ?? "").trim() || DEFAULT_PLATFORM_NAME,
    adopterLogoUrl: (config.adopterLogoUrl ?? "").trim(),
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

/** Platform display name for titles, consent copy, headers, etc. */
export function getPlatformName(): string {
  return cached.platformName || DEFAULT_PLATFORM_NAME;
}

/** Logo from ConfigMap; invalid/unset ⇒ default SVG. */
export function getAdopterLogoSrc(): string {
  const raw = (cached.adopterLogoUrl ?? "").trim();
  if (!raw) return DEFAULT_ADOPTER_LOGO_SRC;
  if (raw.startsWith("/") && !raw.startsWith("//")) return raw;
  try {
    const { protocol } = new URL(raw);
    if (protocol === "http:" || protocol === "https:") return raw;
  } catch {
    /* use default */
  }
  return DEFAULT_ADOPTER_LOGO_SRC;
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
