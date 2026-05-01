import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";

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

const ep = apiEndpoints.policy;

export const policyService = {
  health: () => apiService.get<{ status: string }>(ep.health),

  listPiiTypes: (params?: {
    search?: string;
    page?: number;
    limit?: number;
  }) => apiService.get<PiiTypeListResponse>(ep.piiTypes, { params }),

  getPiiType: (id: string) => apiService.get<PiiTypeOut>(ep.piiTypeById(id)),

  createPiiType: (body: {
    pii_type_label: string;
    regex_pattern: string;
    example_values: string[];
    mask_format: MaskFormat;
  }) => apiService.post<PiiTypeOut>(ep.piiTypes, body),

  updatePiiType: (
    id: string,
    body: Partial<{
      pii_type_label: string;
      regex_pattern: string;
      example_values: string[];
      mask_format: MaskFormat;
    }>
  ) => apiService.put<PiiTypeOut>(ep.piiTypeById(id), body),

  deletePiiType: (id: string) => apiService.delete<void>(ep.piiTypeById(id)),

  listPolicies: (params?: {
    is_global?: boolean;
    is_active?: boolean;
    search?: string;
    page?: number;
    limit?: number;
  }) => apiService.get<PolicyListResponse>(ep.policies, { params }),

  getPolicy: (id: string) => apiService.get<PolicyOut>(ep.policyById(id)),

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
  }) => apiService.post<PolicyOut>(ep.policies, body),

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
  ) => apiService.put<PolicyOut>(ep.policyById(id), body),

  deletePolicy: (id: string) => apiService.delete<void>(ep.policyById(id)),

  setPolicyStatus: (id: string, is_active: boolean) =>
    apiService.patch<{ is_active: boolean }>(ep.policyStatus(id), {
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
  }) => apiService.get<AuditLogListResponse>(ep.auditLogs, { params }),

  getAuditLog: (id: string) =>
    apiService.get<AuditLogDetailOut>(ep.auditLogById(id)),
};
