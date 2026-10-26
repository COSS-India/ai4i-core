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
 *
 * Branding (name + logo) is configured once via PLATFORM_NAME + ADOPTER_LOGO_URL
 * (root env / shared ConfigMap — see branding.ts).
 */

import {
  DEFAULT_ADOPTER_LOGO_SRC,
  DEFAULT_PLATFORM_NAME,
  resolveAdopterLogoSrc,
  resolvePlatformName,
  type BrandingConfig,
} from "./branding";

export {
  DEFAULT_ADOPTER_LOGO_SRC,
  DEFAULT_PLATFORM_NAME,
  type BrandingConfig,
} from "./branding";

export type RuntimeConfig = {
  /** Browser-facing API origin. Empty ⇒ same-origin (Next.js proxy). */
  apiUrl: string;
  /** Telemetry service origin. Empty ⇒ same-origin proxy paths. */
  telemetryServiceUrl: string;
  /** Comma-separated yaml task-type names (e.g. "llm" or "llm,nmt"). Empty ⇒ full catalog. */
  enabledTaskTypes: string;
  /** Product/brand name (PLATFORM_NAME). */
  platformName: string;
  /** Raw ConfigMap ADOPTER_LOGO_URL; empty ⇒ default SVG via getAdopterLogoSrc. */
  adopterLogoUrl: string;
  /** Raw ROTATED_API_KEY_DEFAULT_GRACE_DAYS; parsed by getDefaultRotationGraceDays. */
  rotationGraceDays: string;
  /** Raw ULCA_MODEL_SPEC_URL; empty/invalid ⇒ DEFAULT_ULCA_MODEL_SPEC_URL via getModelSpecUrls. */
  ulcaModelSpecUrl: string;
  /** Raw OPENAI_SPEC_URL; empty/invalid ⇒ DEFAULT_OPENAI_SPEC_URL via getModelSpecUrls. */
  openaiSpecUrl: string;
};

export const DEFAULT_ULCA_MODEL_SPEC_URL =
  "https://github.com/bhashini-dibd/ulca/blob/master/specs/model-schema.yml";
export const DEFAULT_OPENAI_SPEC_URL =
  "https://developers.openai.com/api/reference/overview?site_locale=en";

export const EMPTY_RUNTIME_CONFIG: RuntimeConfig = {
  apiUrl: "",
  telemetryServiceUrl: "",
  enabledTaskTypes: "",
  platformName: DEFAULT_PLATFORM_NAME,
  adopterLogoUrl: "",
  rotationGraceDays: "",
  ulcaModelSpecUrl: "",
  openaiSpecUrl: "",
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
    platformName: resolvePlatformName(
      firstEnv("PLATFORM_NAME", "NEXT_PUBLIC_PLATFORM_NAME"),
    ),
    adopterLogoUrl: firstEnv("ADOPTER_LOGO_URL", "NEXT_PUBLIC_ADOPTER_LOGO_URL"),
    rotationGraceDays: firstEnv("ROTATED_API_KEY_DEFAULT_GRACE_DAYS"),
    ulcaModelSpecUrl: firstEnv("ULCA_MODEL_SPEC_URL"),
    openaiSpecUrl: firstEnv("OPENAI_SPEC_URL"),
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
    platformName: resolvePlatformName(config.platformName),
    adopterLogoUrl: (config.adopterLogoUrl ?? "").trim(),
    rotationGraceDays: (config.rotationGraceDays ?? "").trim(),
    ulcaModelSpecUrl: (config.ulcaModelSpecUrl ?? "").trim(),
    openaiSpecUrl: (config.openaiSpecUrl ?? "").trim(),
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

/** Platform display name for titles, headers, etc. */
export function getPlatformName(): string {
  return resolvePlatformName(cached.platformName);
}

/** Logo from ConfigMap; invalid/unset ⇒ default SVG. */
export function getAdopterLogoSrc(): string {
  return resolveAdopterLogoSrc(cached.adopterLogoUrl);
}

/** Name + logo together — prefer this when both are needed. */
export function getBranding(): BrandingConfig {
  return {
    name: getPlatformName(),
    logoSrc: getAdopterLogoSrc(),
  };
}

/**
 * Grace period prefilled in the rotate dialog, in whole days; null when
 * ROTATED_API_KEY_DEFAULT_GRACE_DAYS is unset or invalid (the field then
 * starts blank and the admin must enter one — the rotate API requires it).
 */
export function getDefaultRotationGraceDays(): number | null {
  const raw = cached.rotationGraceDays;
  if (!/^\d+$/.test(raw)) return null;
  return Number(raw);
}

/** Absolute http(s) URL only — the value lands in an href, so anything else falls back. */
function resolveExternalUrl(raw: string, fallback: string): string {
  try {
    const { protocol } = new URL(raw);
    if (protocol === "http:" || protocol === "https:") return raw;
  } catch {
    /* use fallback */
  }
  return fallback;
}

/**
 * Spec links shown on Create Model (ULCA for NLP models, OpenAI for LLMs).
 * ULCA_MODEL_SPEC_URL / OPENAI_SPEC_URL override the defaults without a rebuild.
 */
export function getModelSpecUrls(): { ulca: string; openai: string } {
  return {
    ulca: resolveExternalUrl(cached.ulcaModelSpecUrl, DEFAULT_ULCA_MODEL_SPEC_URL),
    openai: resolveExternalUrl(cached.openaiSpecUrl, DEFAULT_OPENAI_SPEC_URL),
  };
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
