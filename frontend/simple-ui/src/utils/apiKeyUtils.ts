import type { APIKeyResponse } from "../types/auth";

type ApiKeyLike = {
  api_key?: string | null;
  apiKey?: string | null;
  id?: number | null;
  key_id?: number | null;
  keyId?: number | null;
  key_name?: string | null;
};

/** Strip ".INFERENCE" from catalog labels (e.g. ASR.INFERENCE → ASR). Values stay unchanged. */
export function formatPermissionLabel(label: string): string {
  return label.replace(/\.inference$/i, "").toUpperCase();
}

export function normalizeApiKeyRecord<T extends ApiKeyLike>(key: T): T & APIKeyResponse {
  const raw = key as ApiKeyLike;
  const apiKey = raw.api_key ?? raw.apiKey;
  const id = raw.id ?? raw.key_id ?? raw.keyId;
  return {
    ...key,
    ...(apiKey != null && String(apiKey).trim() ? { api_key: String(apiKey).trim() } : {}),
    ...(id != null && Number.isFinite(Number(id)) ? { id: Number(id) } : {}),
  } as T & APIKeyResponse;
}

/**
 * True while a rotated key's previous value still works (it can't be rotated
 * again until then). A revoked, inactive or expired key has no live value,
 * even if its rotation window has not ended.
 */
export function isRotationInProgress(
  key: Pick<APIKeyResponse, "rotated_key_expires_at" | "is_active" | "is_revoked" | "expires_at">,
  now: number = Date.now(),
): boolean {
  if (!key.rotated_key_expires_at) return false;
  if (key.is_active === false || key.is_revoked === true) return false;
  if (key.expires_at) {
    const keyExpiry = new Date(key.expires_at).getTime();
    if (Number.isFinite(keyExpiry) && keyExpiry <= now) return false;
  }
  const until = new Date(key.rotated_key_expires_at).getTime();
  return Number.isFinite(until) && until > now;
}

/** Grace periods (days) an admin can pick when rotating a key. */
export const ROTATION_GRACE_OPTIONS = [1, 3, 7, 14] as const;

/** True when a grace period of ``days`` from now ends by the key's expiry. */
export function isGraceWithinExpiry(
  days: number,
  expiresAt: string | undefined,
  now: number = Date.now(),
): boolean {
  if (!expiresAt) return true;
  return now + days * 86_400_000 <= new Date(expiresAt).getTime();
}

/** Preset extensions for a previous key's grace period, added to its current end. */
export const GRACE_EXTENSION_OPTIONS = [
  { id: "24h", label: "24h", hours: 24 },
  { id: "48h", label: "48 hours", hours: 48 },
  { id: "7d", label: "7d", hours: 168 },
] as const;

export type GraceExtensionOption = (typeof GRACE_EXTENSION_OPTIONS)[number]["id"] | "custom";

/** Preset selected when the extend dialog opens. */
export const DEFAULT_GRACE_EXTENSION: GraceExtensionOption = "48h";

/** New grace end: the current end plus a preset, or a custom datetime-local value. */
export function graceExtensionEnd(
  currentEnd: string | undefined,
  option: GraceExtensionOption,
  customUntil: string,
): Date | null {
  if (option === "custom") {
    if (!customUntil) return null;
    const custom = new Date(customUntil);
    return Number.isFinite(custom.getTime()) ? custom : null;
  }
  if (!currentEnd) return null;
  const base = new Date(currentEnd).getTime();
  const preset = GRACE_EXTENSION_OPTIONS.find((o) => o.id === option);
  if (!Number.isFinite(base) || !preset) return null;
  return new Date(base + preset.hours * 3_600_000);
}

/** Why ``newEnd`` can't be used (same rules as the backend), or null when it can. */
export function graceExtensionError(
  newEnd: Date | null,
  currentEnd: string | undefined,
  keyExpiresAt: string | undefined,
): string | null {
  if (!newEnd) return "Choose when the previous key should stop working.";
  if (currentEnd && newEnd.getTime() <= new Date(currentEnd).getTime()) {
    return "The new end must be later than the current one.";
  }
  if (keyExpiresAt && newEnd.getTime() > new Date(keyExpiresAt).getTime()) {
    return `The previous key can't outlive the key, which expires ${new Date(keyExpiresAt).toLocaleString()}.`;
  }
  return null;
}

/** "26 hours" / "3 days" until ``to``, for grace-period copy. */
export function formatTimeUntil(to: string | Date, now: number = Date.now()): string {
  const ms = new Date(to).getTime() - now;
  if (!Number.isFinite(ms) || ms <= 0) return "now";
  const hours = Math.round(ms / 3_600_000);
  if (hours < 1) return "less than an hour";
  if (hours < 48) return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  const days = Math.round(hours / 24);
  return `${days} days`;
}

/** Hours between two instants, rounded, for "extended by N hours" copy. */
export function formatExtension(from: string, to: Date): string {
  const hours = Math.round((to.getTime() - new Date(from).getTime()) / 3_600_000);
  if (hours % 24 === 0 && hours >= 48) return `${hours / 24} days`;
  return `${hours} ${hours === 1 ? "hour" : "hours"}`;
}
