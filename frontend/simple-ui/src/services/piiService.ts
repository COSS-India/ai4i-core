import api from "./api";

const BASE_URL = "/api/v1/pii";

export const piiService = {
  getDomains: () => api.get<string[]>(`${BASE_URL}/domains`),

  getPolicy: (domainId: string) =>
    api.get<{ meta?: unknown; rules?: unknown[] }>(
      `${BASE_URL}/policy/${encodeURIComponent(domainId)}`
    ),

  redact: (
    payload: { text: string; domain?: string | null },
    target: string,
    lang: string,
    tenantId?: string | null
  ) =>
    api.post(`${BASE_URL}/redact`, payload, {
      headers: {
        "X-Target": target,
        "X-Language": lang,
        ...(tenantId ? { "X-Tenant-Id": tenantId } : {}),
      },
    }),

  getAllDomains: () =>
    api.get<
      { domain_id: string; is_active: boolean; description?: string | null }[]
    >(`${BASE_URL}/admin/all-domains`),

  activateDomains: (domainIds: string[]) =>
    api.post(`${BASE_URL}/admin/activate-domains`, {
      domain_ids: domainIds,
    }),

  createDomain: (domainId: string, description?: string) =>
    api.post(`${BASE_URL}/admin/domain`, {
      domain_id: domainId,
      description: description?.trim() || `Policy scope: ${domainId}`,
    }),

  deployRules: (domainId: string, rules: unknown[]) =>
    api.post(`${BASE_URL}/admin/deploy`, { domain_id: domainId, rules }),

  generateRegex: (exampleText: string) =>
    api.post(`${BASE_URL}/admin/generate-regex`, {
      example_text: exampleText,
    }),

  listTenantDomainMappings: () =>
    api.get<
      { tenant_id: string; domain_id: string; updated_at?: string }[]
    >(`${BASE_URL}/admin/tenant-domains`),

  upsertTenantDomainMapping: (tenantId: string, domainId: string) =>
    api.post(`${BASE_URL}/admin/tenant-domain`, {
      tenant_id: tenantId,
      domain_id: domainId,
    }),

  deleteTenantDomainMapping: (tenantId: string) =>
    api.post(`${BASE_URL}/admin/tenant-domain/delete`, {
      tenant_id: tenantId,
    }),
};
