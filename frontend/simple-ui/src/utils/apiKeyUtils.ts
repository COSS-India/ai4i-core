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
