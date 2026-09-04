/**
 * Product branding — single config surface for display name + logo (AI4IDS-3043).
 *
 * Configure once via PLATFORM_NAME + ADOPTER_LOGO_URL (root env / ConfigMap).
 * Defaults apply when unset. UI (including consent) and emails read these keys.
 */

/** Default product display name. Override with PLATFORM_NAME. */
export const DEFAULT_PLATFORM_NAME = "AI4I Orchestrate";

/** Default instance logo. Override with ADOPTER_LOGO_URL (http(s) or same-origin path). */
export const DEFAULT_ADOPTER_LOGO_SRC = "/AI4Inclusion_Logo.svg";

export type BrandingConfig = {
  /** Product/brand name shown in UI titles, consent-adjacent copy, headers, emails. */
  name: string;
  /** Resolved logo URL or same-origin path safe to render in <img src>. */
  logoSrc: string;
};

/** Trimmed name, or default when blank. */
export function resolvePlatformName(raw: string | null | undefined): string {
  return (raw ?? "").trim() || DEFAULT_PLATFORM_NAME;
}

/**
 * Accept http(s) URLs and same-origin paths only.
 * Rejects protocol-relative, data:, javascript:, and malformed values.
 */
export function resolveAdopterLogoSrc(raw: string | null | undefined): string {
  const value = (raw ?? "").trim();
  if (!value) return DEFAULT_ADOPTER_LOGO_SRC;
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  try {
    const { protocol } = new URL(value);
    if (protocol === "http:" || protocol === "https:") return value;
  } catch {
    /* use default */
  }
  return DEFAULT_ADOPTER_LOGO_SRC;
}

/** Absolute http(s) logo only — suitable for email clients (no relative paths). */
export function resolveEmailLogoUrl(raw: string | null | undefined): string | null {
  const value = (raw ?? "").trim();
  if (!value) return null;
  try {
    const { protocol } = new URL(value);
    if (protocol === "http:" || protocol === "https:") return value;
  } catch {
    return null;
  }
  return null;
}
