import { z } from 'zod';

export const piiPolicySchema = z
  .object({
    meta: z.unknown().optional(),
    rules: z.array(z.unknown()).optional(),
  })
  .passthrough();

export const piiDomainRowSchema = z
  .object({
    domain_id: z.string(),
    is_active: z.boolean(),
    description: z.string().nullable().optional(),
  })
  .passthrough();

export const piiTenantDomainMappingSchema = z
  .object({
    tenant_id: z.string(),
    domain_id: z.string(),
    updated_at: z.string().optional(),
  })
  .passthrough();

export const piiAuditRowSchema = z
  .object({
    id: z.number(),
    trace_id: z.string(),
    tenant_id: z.string(),
    domain_id: z.string(),
    target_context: z.string(),
    pii_count: z.number(),
    processing_ms: z.number(),
    trace_json: z.unknown(),
    created_at: z.string(),
  })
  .passthrough();

export const piiRedactResponseSchema = z.unknown();

export const stringArraySchema = z.array(z.string());
