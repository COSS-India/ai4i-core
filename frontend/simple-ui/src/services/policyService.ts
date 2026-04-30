import api, { apiClient, apiEndpoints } from "./api";

// =============================================================================
// Policy engine (plans / tiers — `/api/v1/policy-engine`) — usage & billing
// =============================================================================

const POLICY_ENGINE_BASE = "/api/v1/policy-engine";

export interface QuotaConfigNested {
  name: string;
  requests_per_hour: number;
  service_limits: Array<{ service_type: string; unit_type: string; limit_value: number }>;
}

export interface RateLimitNested {
  name: string;
  requests_per_hour_per_api_key: number;
  requests_per_hour_per_tenant: number;
}

export interface PlanPolicy {
  id: string;
  plan_name: string;
  cost: number;
  tier: string;
  quota_config: QuotaConfigNested | Record<string, unknown>;
  rate_limit_config: RateLimitNested | Record<string, unknown>;
}

export interface PlanService {
  service_id: string;
  service_name: string;
  unit_type: string;
  cost_per_unit: number;
  tier: string;
}

export async function getPolicies(): Promise<PlanPolicy[]> {
  const { data } = await apiClient.get<PlanPolicy[]>(`${POLICY_ENGINE_BASE}/policies`);
  return data;
}

export async function createPolicy(payload: {
  plan_name: string;
  cost: number;
  tier: string;
}): Promise<PlanPolicy> {
  const { data } = await apiClient.post<PlanPolicy>(`${POLICY_ENGINE_BASE}/policies`, payload);
  return data;
}

export async function getPolicyById(id: string): Promise<PlanPolicy> {
  const { data } = await apiClient.get<PlanPolicy>(`${POLICY_ENGINE_BASE}/policies/${id}`);
  return data;
}

export async function getPolicyByTier(tier: string): Promise<PlanPolicy> {
  const { data } = await apiClient.get<PlanPolicy>(
    `${POLICY_ENGINE_BASE}/policies/tier/${encodeURIComponent(tier)}`
  );
  return data;
}

export async function updatePolicy(
  id: string,
  payload: Partial<{ plan_name: string; cost: number; tier: string }>
): Promise<PlanPolicy> {
  const { data } = await apiClient.put<PlanPolicy>(`${POLICY_ENGINE_BASE}/policies/${id}`, payload);
  return data;
}

export async function deletePolicy(id: string): Promise<void> {
  await apiClient.delete(`${POLICY_ENGINE_BASE}/policies/${id}`);
}

export async function getPoliciesByTenant(tenantId: string): Promise<unknown> {
  const { data } = await apiClient.get(
    `${POLICY_ENGINE_BASE}/policies/tenant/${encodeURIComponent(tenantId)}`
  );
  return data;
}

export async function getPlanServices(planId: string): Promise<PlanService[]> {
  const { data } = await apiClient.get<PlanService[]>(
    `${POLICY_ENGINE_BASE}/policies/${encodeURIComponent(planId)}/services`
  );
  return data;
}

// =============================================================================
// PII Policy service (`/api/v1/policy-service`) — PolicyManagement UI
// =============================================================================

/** Matches Postman `POLICY_BASE_URL` + path (e.g. `/pii-types`), no `/v1` segment. */
const POLICY_API = apiEndpoints.policy.base;

export interface PolicyListMeta {
  total: number;
  page: number;
  limit: number;
}

export interface PolicyPiiTypeOut {
  pii_type_id: string;
  pii_type_label: string;
  mask_format: string;
}

export interface PolicyOut {
  policy_id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  is_global: boolean;
  supported_languages: string[];
  /** Assigned tenants (API returns `tenant_ids`; not a single `tenant_id`). */
  tenant_ids?: string[];
  pii_types: PolicyPiiTypeOut[];
  created_at: string;
}

export interface PolicyListResponse {
  data: PolicyOut[];
  meta: PolicyListMeta;
}

export interface PiiTypeOut {
  pii_type_id: string;
  pii_type_label: string;
  regex_pattern: string;
  mask_format: string;
  created_at: string;
}

export interface PiiTypeListResponse {
  data: PiiTypeOut[];
  meta: PolicyListMeta;
}

export interface AuditLogOut {
  pii_audit_id: string;
  trace_id?: string | null;
  tenant_id?: string | null;
  policy_id?: string | null;
  target_context?: string | null;
  pii_count?: number | null;
  processing_ms?: number | null;
  created_at: string;
}

export interface AuditLogDetailOut extends AuditLogOut {
  trace_json?: unknown;
}

export interface AuditLogListResponse {
  data: AuditLogOut[];
  meta: PolicyListMeta;
}

export type MaskFormat = "full" | "partial" | "redact";

/** PII / policy-service HTTP API (different from policy-engine plan APIs above). */
export const policyService = {
  health: () => api.get<{ status: string }>(`${POLICY_API}/health`),

  listPiiTypes: (params?: {
    search?: string;
    page?: number;
    limit?: number;
  }) => api.get<PiiTypeListResponse>(`${POLICY_API}/pii-types`, { params }),

  getPiiType: (id: string) => api.get<PiiTypeOut>(`${POLICY_API}/pii-types/${id}`),

  createPiiType: (body: {
    pii_type_label: string;
    regex_pattern: string;
    example_values: string[];
    mask_format: MaskFormat;
  }) => api.post<PiiTypeOut>(`${POLICY_API}/pii-types`, body),

  updatePiiType: (
    id: string,
    body: Partial<{
      pii_type_label: string;
      regex_pattern: string;
      example_values: string[];
      mask_format: MaskFormat;
    }>
  ) => api.put<PiiTypeOut>(`${POLICY_API}/pii-types/${id}`, body),

  deletePiiType: (id: string) => api.delete<void>(`${POLICY_API}/pii-types/${id}`),

  listPolicies: (params?: {
    is_global?: boolean;
    is_active?: boolean;
    search?: string;
    page?: number;
    limit?: number;
  }) => api.get<PolicyListResponse>(`${POLICY_API}/policies`, { params }),

  getPolicy: (id: string) => api.get<PolicyOut>(`${POLICY_API}/policies/${id}`),

  /**
   * API expects `pii_types: [{ pii_type_id }]`, not Postman’s `pii_type_ids`.
   * `is_active` on create is not accepted by the service schema (use PATCH status after create if needed).
   */
  createPolicy: (body: {
    name: string;
    description?: string | null;
    is_global: boolean;
    supported_languages: string[];
    tenant_ids?: string[];
    pii_types?: { pii_type_id: string }[];
  }) => api.post<PolicyOut>(`${POLICY_API}/policies`, body),

  updatePolicy: (
    id: string,
    body: Partial<{
      name: string;
      description: string | null;
      supported_languages: string[];
      is_global: boolean;
      tenant_ids: string[];
      pii_types: { pii_type_id: string }[] | null;
    }>
  ) => api.put<PolicyOut>(`${POLICY_API}/policies/${id}`, body),

  deletePolicy: (id: string) => api.delete<void>(`${POLICY_API}/policies/${id}`),

  setPolicyStatus: (id: string, is_active: boolean) =>
    api.patch<{ is_active: boolean }>(`${POLICY_API}/policies/${id}/status`, {
      is_active,
    }),

  listAuditLogs: (params?: {
    tenant_id?: string;
    policy_id?: string;
    trace_id?: string;
    from?: string;
    to?: string;
    min_pii_count?: number;
    page?: number;
    limit?: number;
  }) => api.get<AuditLogListResponse>(`${POLICY_API}/audit-logs`, { params }),

  getAuditLog: (id: string) =>
    api.get<AuditLogDetailOut>(`${POLICY_API}/audit-logs/${id}`),
};
