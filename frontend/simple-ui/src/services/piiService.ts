import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";

const admin = apiEndpoints.pii.admin;

export const piiService = {
  getDomains: () => apiService.get<string[]>(apiEndpoints.pii.domains),

  getPolicy: (domainId: string) =>
    apiService.get<{ meta?: unknown; rules?: unknown[] }>(
      apiEndpoints.pii.policyByDomain(domainId)
    ),

  redact: (
    payload: { text: string; domain?: string | null },
    target: string,
    lang: string,
    tenantId?: string | null
  ) =>
    apiService.post(apiEndpoints.pii.redact, payload, {
      headers: {
        "X-Target": target,
        "X-Language": lang,
        ...(tenantId ? { "X-Tenant-Id": tenantId } : {}),
      },
    }),

  getAllDomains: () =>
    apiService.get<
      { domain_id: string; is_active: boolean; description?: string | null }[]
    >(admin.allDomains),

  activateDomains: (domainIds: string[]) =>
    apiService.post(admin.activateDomains, {
      domain_ids: domainIds,
    }),

  createDomain: (domainId: string, description?: string) =>
    apiService.post(admin.domain, {
      domain_id: domainId,
      description: description?.trim() || `Policy scope: ${domainId}`,
    }),

  deployRules: (domainId: string, rules: unknown[]) =>
    apiService.post(admin.deploy, { domain_id: domainId, rules }),

  generateRegex: (exampleText: string) =>
    apiService.post(admin.generateRegex, {
      example_text: exampleText,
    }),

  listTenantDomainMappings: () =>
    apiService.get<
      { tenant_id: string; domain_id: string; updated_at?: string }[]
    >(admin.tenantDomains),

  upsertTenantDomainMapping: (tenantId: string, domainId: string) =>
    apiService.post(admin.tenantDomain, {
      tenant_id: tenantId,
      domain_id: domainId,
    }),

  deleteTenantDomainMapping: (tenantId: string) =>
    apiService.post(admin.tenantDomainDelete, {
      tenant_id: tenantId,
    }),

  getAuditLogs: (limit = 50) =>
    apiService.get<
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
    >(admin.auditLogs, { params: { limit } }),
};
