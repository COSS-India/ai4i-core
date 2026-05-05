import { z } from "zod";
import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  auditLogDetailOutSchema,
  auditLogListResponseSchema,
  piiTypeListResponseSchema,
  piiTypeOutSchema,
  policyHealthSchema,
  policyListResponseSchema,
  policyOutSchema,
  policyStatusPatchSchema,
} from "./dto/schemas/policy";

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
  health: () =>
    apiService.get(ep.health, { responseSchema: policyHealthSchema }),

  listPiiTypes: (params?: {
    search?: string;
    page?: number;
    limit?: number;
  }) => apiService.get(ep.piiTypes, { params, responseSchema: piiTypeListResponseSchema }),

  getPiiType: (id: string) =>
    apiService.get(ep.piiTypeById(id), { responseSchema: piiTypeOutSchema }),

  createPiiType: (body: {
    pii_type_label: string;
    regex_pattern: string;
    example_values: string[];
    mask_format: MaskFormat;
  }) => apiService.post(ep.piiTypes, body, { responseSchema: piiTypeOutSchema }),

  updatePiiType: (
    id: string,
    body: Partial<{
      pii_type_label: string;
      regex_pattern: string;
      example_values: string[];
      mask_format: MaskFormat;
    }>
  ) => apiService.put(ep.piiTypeById(id), body, { responseSchema: piiTypeOutSchema }),

  deletePiiType: (id: string) =>
    apiService.delete(ep.piiTypeById(id), { responseSchema: z.unknown() }),

  listPolicies: (params?: {
    is_global?: boolean;
    is_active?: boolean;
    search?: string;
    page?: number;
    limit?: number;
  }) => apiService.get(ep.policies, { params, responseSchema: policyListResponseSchema }),

  getPolicy: (id: string) =>
    apiService.get(ep.policyById(id), { responseSchema: policyOutSchema }),

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
  }) => apiService.post(ep.policies, body, { responseSchema: policyOutSchema }),

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
  ) => apiService.put(ep.policyById(id), body, { responseSchema: policyOutSchema }),

  deletePolicy: (id: string) =>
    apiService.delete(ep.policyById(id), { responseSchema: z.unknown() }),

  setPolicyStatus: (id: string, is_active: boolean) =>
    apiService.patch(ep.policyStatus(id), {
      is_active,
    }, { responseSchema: policyStatusPatchSchema }),

  listAuditLogs: (params?: {
    tenant_id?: string;
    policy_id?: string;
    trace_id?: string;
    from?: string;
    to?: string;
    min_pii_count?: number;
    page?: number;
    limit?: number;
  }) => apiService.get(ep.auditLogs, { params, responseSchema: auditLogListResponseSchema }),

  getAuditLog: (id: string) =>
    apiService.get(ep.auditLogById(id), { responseSchema: auditLogDetailOutSchema }),
};
