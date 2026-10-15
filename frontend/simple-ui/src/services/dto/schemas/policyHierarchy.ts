import { z } from "zod";

/** Platform-core `CategoryItem`. */
export const policyCategoryItemSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  description: z.string().nullable().optional(),
  is_active: z.boolean(),
});

/** Platform-core `SubCategoryItem`. */
export const policySubCategoryItemSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  description: z.string().nullable().optional(),
  category_id: z.number().int(),
  is_active: z.boolean(),
});

export const policyCategoryListResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    items: z.array(policyCategoryItemSchema),
  }),
});

export const policySubCategoryListResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    items: z.array(policySubCategoryItemSchema),
  }),
});

const policyWriteMetaSchema = z
  .object({
    message: z.string().optional(),
  })
  .passthrough()
  .optional();

/** POST /policies/categories */
export const policyCategoryCreateResponseSchema = z.object({
  success: z.boolean(),
  data: policyCategoryItemSchema,
  meta: policyWriteMetaSchema,
});

/** POST /policies/sub-categories */
export const policySubCategoryCreateResponseSchema = z.object({
  success: z.boolean(),
  data: policySubCategoryItemSchema,
  meta: policyWriteMetaSchema,
});

/** PATCH /policies/categories/{id}/status */
export const policyCategoryStatusResponseSchema = z.object({
  success: z.boolean(),
  data: policyCategoryItemSchema,
  meta: policyWriteMetaSchema,
});

/** PATCH /policies/sub-categories/{id}/status */
export const policySubCategoryStatusResponseSchema = z.object({
  success: z.boolean(),
  data: policySubCategoryItemSchema,
  meta: policyWriteMetaSchema,
});

const policyFieldsSchema = z.preprocess(
  (value) => (value && typeof value === "object" && !Array.isArray(value) ? value : {}),
  z.record(z.unknown()),
);

/** Platform-core `PolicyTypeItem`. A PII definition. */
export const policyTypeItemSchema = z.object({
  id: z.number().int(),
  policy_type: z.string(),
  policy_fields: policyFieldsSchema,
});

/** GET /policies/policy-types. */
export const policyTypeListResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    items: z.array(policyTypeItemSchema),
  }),
});

/** GET /policies/policy-types/{id} and PUT /policies/policy-types. */
export const policyTypeItemResponseSchema = z.object({
  success: z.boolean(),
  data: policyTypeItemSchema,
  meta: policyWriteMetaSchema,
});

/** POST /policies/policy-types returns the new id. The row is loaded with GET by id. */
export const policyTypeCreateResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    id: z.number().int(),
  }),
  meta: policyWriteMetaSchema,
});

export const guardrailScopeSchema = z.enum(["input", "output", "both"]);

/** A field picked from one of the policy's linked policy types. `language` is set for model_supported_field. */
export const selectedPolicyFieldSchema = z.object({
  source: z.enum(["custom_field", "model_supported_field"]),
  policy_type_id: z.number().int(),
  entity_name: z.string(),
  language: z.string().nullable().optional(),
});

/** Platform-core `PolicyItem`. null languages / selected_policy_fields: saved before they were stored. */
export const policyRecordSchema = z.object({
  id: z.number().int(),
  policy_id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  domain: z.array(z.string()).default([]),
  guardrail_scope: guardrailScopeSchema,
  is_global: z.boolean(),
  sub_category_id: z.number().int(),
  is_active: z.boolean(),
  policy_type_id: z.array(z.number().int()).nullable().optional(),
  languages: z.array(z.string()).nullable().optional(),
  selected_policy_fields: z.array(selectedPolicyFieldSchema).nullable().optional(),
});

/** GET /policies. Filters: name, sub_category_id, offset, limit. */
export const policyListResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    items: z.array(policyRecordSchema),
  }),
  meta: z.object({
    total: z.number().int(),
    offset: z.number().int(),
    limit: z.number().int(),
  }),
});

/** POST /policies returns the generated policy_id. The row is read back from the list. */
export const policyCreateResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    policy_id: z.string(),
  }),
  meta: policyWriteMetaSchema,
});

/** GET /policies/{id} and PUT /policies. */
export const policyItemResponseSchema = z.object({
  success: z.boolean(),
  data: policyRecordSchema,
  meta: policyWriteMetaSchema,
});

/** POST /pii/simulate (inference service). */
export const policySimulationResponseSchema = z.object({
  originalText: z.string(),
  sanitizedText: z.string(),
  detected: z.array(
    z.object({
      entityType: z.string(),
      policyTypes: z.array(z.string()),
      instances: z.number().int(),
      replacements: z.array(z.object({ original: z.string(), output: z.string() })),
    }),
  ),
});

export type PolicyCategoryItem = z.infer<typeof policyCategoryItemSchema>;
export type PolicySubCategoryItem = z.infer<typeof policySubCategoryItemSchema>;
export type PolicyTypeItem = z.infer<typeof policyTypeItemSchema>;
export type PolicyRecord = z.infer<typeof policyRecordSchema>;
export type SelectedPolicyFieldRecord = z.infer<typeof selectedPolicyFieldSchema>;
export type GuardrailScope = z.infer<typeof guardrailScopeSchema>;
export type PolicySimulation = z.infer<typeof policySimulationResponseSchema>;
