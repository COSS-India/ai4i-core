import type { APIKeyResponse } from "../types/auth";

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
