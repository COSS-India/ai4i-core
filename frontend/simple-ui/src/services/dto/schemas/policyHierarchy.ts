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

export type PolicyCategoryItem = z.infer<typeof policyCategoryItemSchema>;
export type PolicySubCategoryItem = z.infer<typeof policySubCategoryItemSchema>;
