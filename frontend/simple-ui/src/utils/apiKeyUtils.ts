import type { APIKeyResponse } from "../types/auth";

/** sessionStorage cache: keys created in this browser session (hex shown once at create). */
export const API_KEY_HEX_CACHE_KEY = "ai4i_api_key_hex_cache";

/** Inference permission IDs → display names when GET permissions is unavailable. */
export const INFERENCE_PERMISSION_LABEL_BY_ID: Record<number, string> = {
  60: "NMT.INFERENCE",
  61: "ASR.INFERENCE",
  62: "TTS.INFERENCE",
  63: "LLM.INFERENCE",
  64: "NER.INFERENCE",
  65: "OCR.INFERENCE",
  66: "TRANSLITERATION.INFERENCE",
  67: "LANGUAGE-DETECTION.INFERENCE",
  68: "LANGUAGE-DIARIZATION.INFERENCE",
  69: "SPEAKER-DIARIZATION.INFERENCE",
  70: "AUDIO-LANG-DETECTION.INFERENCE",
  71: "PIPELINE.INFERENCE",
};

type ApiKeyLike = {
  api_key?: string | null;
  apiKey?: string | null;
  id?: number | null;
  key_id?: number | null;
  keyId?: number | null;
  key_name?: string | null;
};

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

export function resolveApiKeyHex(key: ApiKeyLike): string | null {
  const raw = key.api_key ?? key.apiKey;
  if (!raw) return null;
  const normalized = String(raw).trim().toLowerCase();
  return /^[a-f0-9]{32}$/.test(normalized) ? normalized : null;
}

/** Path tokens to try for revoke/update (hex first, then numeric id for older gateways). */
export function buildApiKeyRevokePathTokens(key: ApiKeyLike): string[] {
  const tokens: string[] = [];
  const hex = resolveApiKeyHex(key);
  if (hex) tokens.push(hex);
  const id = key.id ?? key.key_id ?? key.keyId;
  if (id != null && Number.isFinite(Number(id))) tokens.push(String(id));
  return [...new Set(tokens)];
}

export function formatApiKeyDisplayId(key: ApiKeyLike): string {
  const id = key.id ?? key.key_id ?? key.keyId;
  if (id != null && Number.isFinite(Number(id))) return String(id);
  const hex = resolveApiKeyHex(key);
  if (hex) return hex;
  const raw = (key.api_key ?? key.apiKey)?.trim();
  return raw || "—";
}

export function readApiKeyHexCache(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = sessionStorage.getItem(API_KEY_HEX_CACHE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
}

export function cacheCreatedApiKeyHex(
  keyName: string,
  hex: string,
  id?: number | null,
): void {
  if (typeof window === "undefined" || !hex) return;
  const map = readApiKeyHexCache();
  map[keyName] = hex.toLowerCase();
  if (id != null) map[`id:${id}`] = hex.toLowerCase();
  sessionStorage.setItem(API_KEY_HEX_CACHE_KEY, JSON.stringify(map));
}

export function mergeApiKeyHexFromCache<T extends APIKeyResponse>(keys: T[]): T[] {
  const cache = readApiKeyHexCache();
  if (!Object.keys(cache).length) return keys;
  return keys.map((key) => {
    if (resolveApiKeyHex(key)) return key;
    const byName = key.key_name ? cache[key.key_name] : undefined;
    const byId = key.id != null ? cache[`id:${key.id}`] : undefined;
    const hex = byName ?? byId;
    return hex ? { ...key, api_key: hex } : key;
  });
}

export function permissionLabelWithFallback(
  raw: string | number,
  catalog: { id: number; name: string }[],
): string {
  const id =
    typeof raw === "number" && Number.isInteger(raw)
      ? raw
      : /^\d+$/.test(String(raw))
        ? parseInt(String(raw), 10)
        : null;
  if (id != null) {
    const fromCatalog = catalog.find((p) => p.id === id);
    if (fromCatalog?.name) return fromCatalog.name;
    const fallback = INFERENCE_PERMISSION_LABEL_BY_ID[id];
    if (fallback) return fallback;
    return String(id);
  }
  const name = String(raw);
  const fromCatalog = catalog.find((p) => p.name === name);
  return fromCatalog?.name ?? name;
}
