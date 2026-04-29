import api from "./api";
import { apiEndpoints } from "./apiEndpoints";

export const piiService = {
  getDomains: () => api.get<string[]>(apiEndpoints.pii.domains),

  getPolicy: (domainId: string) =>
    api.get<{ meta?: unknown; rules?: unknown[] }>(
      `${apiEndpoints.pii.policy}/${encodeURIComponent(domainId)}`
    ),

  redact: (
    payload: { text: string; domain?: string | null },
    target: string,
    lang: string,
    tenantId?: string | null
  ) =>
    api.post(apiEndpoints.pii.redact, payload, {
      headers: {
        'X-Target': target,
        'X-Language': lang,
        ...(tenantId ? { 'X-Tenant-Id': tenantId } : {}),
      },
    }),

  getAllDomains: () =>
    baseApiService.get<
      { domain_id: string; is_active: boolean; description?: string | null }[]
    >(apiEndpoints.pii.admin.allDomains),

  activateDomains: (domainIds: string[]) =>
    api.post(apiEndpoints.pii.admin.activateDomains, {
      domain_ids: domainIds,
    }),

  createDomain: (domainId: string, description?: string) =>
    api.post(apiEndpoints.pii.admin.domain, {
      domain_id: domainId,
      description: description?.trim() || `Policy scope: ${domainId}`,
    }),

  deployRules: (domainId: string, rules: unknown[]) =>
    api.post(apiEndpoints.pii.admin.deploy, { domain_id: domainId, rules }),

  generateRegex: (exampleText: string) =>
    api.post(apiEndpoints.pii.admin.generateRegex, {
      example_text: exampleText,
    }),

  listTenantDomainMappings: () =>
    baseApiService.get<
      { tenant_id: string; domain_id: string; updated_at?: string }[]
    >(apiEndpoints.pii.admin.tenantDomains),

  upsertTenantDomainMapping: (tenantId: string, domainId: string) =>
    api.post(apiEndpoints.pii.admin.tenantDomain, {
      tenant_id: tenantId,
      domain_id: domainId,
    }),

  deleteTenantDomainMapping: (tenantId: string) =>
    api.post(apiEndpoints.pii.admin.tenantDomainDelete, {
      tenant_id: tenantId,
    }),

  getAuditLogs: (limit = 50) =>
    baseApiService.get<
      {
        id: number;
        trace_id: string;
        tenant_id: string;
        domain_id: string;
        target_context: string;
        pii_count: number;
        processing_ms: number;
        trace_json: unknown;
        created_at: string;
      }[]
    >(apiEndpoints.pii.admin.auditLogs, { params: { limit } }),
};
