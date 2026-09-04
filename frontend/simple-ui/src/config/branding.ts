/**
 * Product branding — single config surface for display name + logo (AI4IDS-3043).
 *
 * Configure once via PLATFORM_NAME + ADOPTER_LOGO_URL (root env / ConfigMap).
 * Bundled logos live at public/assests/<PLATFORM_NAME>/logo.png — set
 * ADOPTER_LOGO_URL to that path when you want them (e.g. PLATFORM_NAME=AISWITCH
 * → ADOPTER_LOGO_URL=/assests/AISWITCH/logo.png). Empty ADOPTER_LOGO_URL keeps
 * the default SVG. UI (including consent) and emails read these keys.
 */

/** Default product display name. Override with PLATFORM_NAME. */
export const DEFAULT_PLATFORM_NAME = "AI4I Orchestrate";

/** Default instance logo. Override with ADOPTER_LOGO_URL (http(s) or same-origin path). */
export const DEFAULT_ADOPTER_LOGO_SRC = "/AI4Inclusion_Logo.svg";

/**
 * Bundled per-platform logos live under public/assests/<PLATFORM_NAME>/logo.png
 * (folder spelling is intentional — matches the on-disk path).
 */
export const PLATFORM_ASSETS_DIR = "/assests";

/** Safe single path segment for public/assests/<name>/ (e.g. AISWITCH, AI4I). */
const PLATFORM_LOGO_FOLDER_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

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
 * Same-origin path for a bundled platform logo under public/assests/, or null
 * when PLATFORM_NAME is not a safe folder slug. Use as ADOPTER_LOGO_URL — not
 * applied automatically when that env is empty.
 */
export function platformLogoSrcFromName(
  platformName: string | null | undefined,
): string | null {
  const name = (platformName ?? "").trim();
  if (!name || !PLATFORM_LOGO_FOLDER_RE.test(name)) return null;
  return `${PLATFORM_ASSETS_DIR}/${name}/logo.png`;
}

/**
 * Accept http(s) URLs and same-origin paths only.
 * Empty / invalid ⇒ default SVG (unchanged). Does not auto-derive from PLATFORM_NAME.
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
