import { z } from "zod";
import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  piiAuditRowSchema,
  piiDomainRowSchema,
  piiPolicySchema,
  piiRedactResponseSchema,
  piiTenantDomainMappingSchema,
  stringArraySchema,
} from "./dto/schemas/pii";

const admin = apiEndpoints.pii.admin;

export const piiService = {
  getDomains: () =>
    apiService.get(apiEndpoints.pii.domains, { responseSchema: stringArraySchema }),

  getPolicy: (domainId: string) =>
    apiService.get(apiEndpoints.pii.policyByDomain(domainId), {
      responseSchema: piiPolicySchema,
    }),

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
      responseSchema: piiRedactResponseSchema,
    }),

  getAllDomains: () =>
    apiService.get(admin.allDomains, { responseSchema: z.array(piiDomainRowSchema) }),

  activateDomains: (domainIds: string[]) =>
    apiService.post(
      admin.activateDomains,
      {
        domain_ids: domainIds,
      },
      { responseSchema: z.unknown() }
    ),

  createDomain: (domainId: string, description?: string) =>
    apiService.post(
      admin.domain,
      {
        domain_id: domainId,
        description: description?.trim() || `Policy scope: ${domainId}`,
      },
      { responseSchema: z.unknown() }
    ),

  deployRules: (domainId: string, rules: unknown[]) =>
    apiService.post(admin.deploy, { domain_id: domainId, rules }, { responseSchema: z.unknown() }),

  generateRegex: (exampleText: string) =>
    apiService.post(
      admin.generateRegex,
      {
        example_text: exampleText,
      },
      { responseSchema: z.unknown() }
    ),

  listTenantDomainMappings: () =>
    apiService.get(admin.tenantDomains, { responseSchema: z.array(piiTenantDomainMappingSchema) }),

  upsertTenantDomainMapping: (tenantId: string, domainId: string) =>
    apiService.post(
      admin.tenantDomain,
      {
        tenant_id: tenantId,
        domain_id: domainId,
      },
      { responseSchema: z.unknown() }
    ),

  deleteTenantDomainMapping: (tenantId: string) =>
    apiService.post(
      admin.tenantDomainDelete,
      {
        tenant_id: tenantId,
      },
      { responseSchema: z.unknown() }
    ),

  getAuditLogs: (limit = 50) =>
    apiService.get(admin.auditLogs, {
      params: { limit },
      responseSchema: z.array(piiAuditRowSchema),
    }),
};
