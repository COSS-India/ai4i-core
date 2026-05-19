import { z } from 'zod';

export const policyListMetaSchema = z.object({
  total: z.number(),
  page: z.number(),
  limit: z.number(),
});

export const policyPiiTypeOutSchema = z.object({
  pii_type_id: z.string(),
  pii_type_label: z.string(),
  mask_format: z.string(),
});

export const policyOutSchema = z
  .object({
    policy_id: z.string(),
    name: z.string(),
    description: z.string().nullable().optional(),
    is_active: z.boolean(),
    is_global: z.boolean(),
    supported_languages: z.array(z.string()),
    tenant_ids: z.array(z.string()).optional(),
    pii_types: z.array(policyPiiTypeOutSchema),
    created_at: z.string(),
  })
  .passthrough();

export const policyListResponseSchema = z.object({
  data: z.array(policyOutSchema),
  meta: policyListMetaSchema,
});

export const piiTypeOutSchema = z.object({
  pii_type_id: z.string(),
  pii_type_label: z.string(),
  regex_pattern: z.string(),
  mask_format: z.string(),
  created_at: z.string(),
});

export const piiTypeListResponseSchema = z.object({
  data: z.array(piiTypeOutSchema),
  meta: policyListMetaSchema,
});

export const auditLogOutSchema = z
  .object({
    pii_audit_id: z.string(),
    trace_id: z.string().nullable().optional(),
    tenant_id: z.string().nullable().optional(),
    policy_id: z.string().nullable().optional(),
    target_context: z.string().nullable().optional(),
    pii_count: z.number().nullable().optional(),
    processing_ms: z.number().nullable().optional(),
    created_at: z.string(),
  })
  .passthrough();

export const auditLogDetailOutSchema = auditLogOutSchema.passthrough();

export const auditLogListResponseSchema = z.object({
  data: z.array(auditLogOutSchema),
  meta: policyListMetaSchema,
});

export const policyHealthSchema = z.object({
  status: z.string(),
});

export const policyStatusPatchSchema = z.object({
  is_active: z.boolean(),
});
