import authService from "./authService";
import type {
  ApiKeyGroupedListResult,
  ApiKeyRecord,
  CreateApiKeyPayload,
  ListApiKeysParams,
} from "../types/apiKey";
import type { APIKeyCreate, APIKeyResponse } from "../types/auth";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function asString(value: unknown): string {
  return value == null ? "" : String(value);
}

function unwrapData(payload: unknown): unknown {
  const root = asRecord(payload);
  if (root && "data" in root) return root.data;
  return payload;
}

function normalizeKey(raw: unknown): ApiKeyRecord {
  const row = asRecord(raw) ?? {};
  return {
    id: asNumber(row.id ?? row.key_id) ?? 0,
    key_name: asString(row.key_name),
    api_key: row.api_key != null ? asString(row.api_key) : undefined,
    application_id: asString(row.application_id),
    allocated_percentage: asNumber(row.allocated_percentage),
    allocated_budget: asNumber(row.allocated_budget),
    permissions: Array.isArray(row.permissions)
      ? row.permissions.map((p) => asString(p))
      : [],
    expires_at: row.expires_at != null ? asString(row.expires_at) : undefined,
    is_active: row.is_active === false ? false : true,
    is_revoked: row.is_revoked === true,
    created_by: row.created_by != null ? asString(row.created_by) : undefined,
    created_at: row.created_at != null ? asString(row.created_at) : undefined,
    updated_at: row.updated_at == null ? null : asString(row.updated_at),
  };
}

function normalizeGroupedList(payload: unknown): ApiKeyGroupedListResult {
  const data = unwrapData(payload);
  if (Array.isArray(data)) {
    const groups = data.map((group) => {
      const g = asRecord(group) ?? {};
      const appId = asString(g.application_id);
      const appName = asString(g.application_name).trim() || undefined;
      const keyRows = Array.isArray(g.api_keys) ? g.api_keys : [];
      return {
        application_id: appId,
        api_keys: keyRows.map((k) => {
          const key = normalizeKey(k);
          return {
            ...key,
            application_id: key.application_id || appId,
            application_name: appName,
          };
        }),
      };
    });
    return { groups };
  }

  const root = asRecord(data) ?? {};
  if (Array.isArray(root.api_keys)) {
    return {
      groups: [{ application_id: "", api_keys: root.api_keys.map((k) => normalizeKey(k)) }],
    };
  }

  return { groups: [] };
}

export function getApiKeyErrorCode(error: unknown): string | null {
  const err = error as {
    response?: { data?: { detail?: { error?: string } | string; code?: string; error?: string } };
  };
  const data = err.response?.data;
  if (!data) return null;
  const detail = data.detail;
  if (typeof detail === "object" && detail?.error) return detail.error;
  if (typeof detail === "string") return detail;
  return data.code ?? data.error ?? null;
}

export async function listGroupedApiKeys(
  _tenantId: string,
  params: ListApiKeysParams = {},
): Promise<ApiKeyGroupedListResult> {
  const query = params.application_id
    ? `?application_id=${encodeURIComponent(params.application_id)}`
    : "";
  const response = await authService.listApiKeysGrouped(query);
  return normalizeGroupedList(response);
}

export async function createScopedApiKey(
  _tenantId: string,
  payload: CreateApiKeyPayload,
): Promise<ApiKeyRecord> {
  const applicationId = Number(payload.application_id);
  const body: APIKeyCreate = {
    key_name: payload.key_name,
    permissions: payload.permissions,
    expires_days: payload.expires_days,
    application_id: String(applicationId),
    allocated_percentage: payload.allocated_percentage,
  };
  const created = await authService.createApiKey(body);
  return normalizeKey(created);
}

/** Flatten grouped list for table rendering. */
export function flattenApiKeyGroups(groups: ApiKeyGroupedListResult["groups"]): ApiKeyRecord[] {
  return groups.flatMap((g) => g.api_keys);
}

/** Map ApiKeyRecord to legacy APIKeyResponse for revoke/update hooks. */
export function toLegacyApiKeyResponse(key: ApiKeyRecord): APIKeyResponse {
  return {
    id: key.id,
    key_name: key.key_name,
    api_key: key.api_key,
    permissions: key.permissions,
    is_active: key.is_active,
    is_revoked: key.is_revoked,
    created_at: key.created_at,
    expires_at: key.expires_at,
    application_id: key.application_id,
    application_name: key.application_name,
    allocated_percentage: key.allocated_percentage,
    allocated_budget: key.allocated_budget,
    created_by: key.created_by,
  } as APIKeyResponse;
}
