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

const listMetaSchema = z
  .object({
    total: z.number().int().optional(),
  })
  .passthrough()
  .optional();

/** GET /policy-types. `data` is the array of definitions. */
export const policyTypeListResponseSchema = z.object({
  success: z.boolean(),
  data: z.array(policyTypeItemSchema),
  meta: listMetaSchema,
});

/** GET /policy-types/{id} and POST /policy-types. Both return the full definition. */
export const policyTypeItemResponseSchema = z.object({
  success: z.boolean(),
  data: policyTypeItemSchema,
  meta: policyWriteMetaSchema,
});

export const guardrailScopeSchema = z.enum(["input", "output", "both"]);

/** Platform-core `PolicyItem`. */
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
  output_parse_pii: z.boolean().optional(),
  policy_type_id: z.array(z.number().int()).nullable().optional(),
});

/** GET /policies. `data` is the array. Filters: sub_category_id, is_active, is_global, guardrail_scope, domain. */
export const policyListResponseSchema = z.object({
  success: z.boolean(),
  data: z.array(policyRecordSchema),
  meta: listMetaSchema,
});

/** POST /policies, GET /policies/{id}, and PATCH /policies/{id}. */
export const policyItemResponseSchema = z.object({
  success: z.boolean(),
  data: policyRecordSchema,
  meta: policyWriteMetaSchema,
});

export type PolicyCategoryItem = z.infer<typeof policyCategoryItemSchema>;
export type PolicySubCategoryItem = z.infer<typeof policySubCategoryItemSchema>;
export type PolicyTypeItem = z.infer<typeof policyTypeItemSchema>;
export type PolicyRecord = z.infer<typeof policyRecordSchema>;
export type GuardrailScope = z.infer<typeof guardrailScopeSchema>;
