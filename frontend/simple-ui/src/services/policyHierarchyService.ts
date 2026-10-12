import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  policyCategoryCreateResponseSchema,
  policyCategoryListResponseSchema,
  policySubCategoryCreateResponseSchema,
  policySubCategoryListResponseSchema,
  type PolicyCategoryItem,
  type PolicySubCategoryItem,
} from "./dto/schemas/policyHierarchy";

export interface PolicyCategoryWrite {
  name: string;
  description?: string | null;
}

export interface PolicySubCategoryWrite extends PolicyCategoryWrite {
  category_id: number;
}

export async function listPolicyCategories(): Promise<PolicyCategoryItem[]> {
  const response = await apiClient.get(apiEndpoints.policyHierarchy.categories);
  return policyCategoryListResponseSchema.parse(response.data).data.items;
}

export async function listPolicySubCategories(
  categoryId?: number,
): Promise<PolicySubCategoryItem[]> {
  const response = await apiClient.get(apiEndpoints.policyHierarchy.subCategories, {
    params: categoryId == null ? undefined : { category_id: categoryId },
  });
  return policySubCategoryListResponseSchema.parse(response.data).data.items;
}

export async function createPolicyCategory(
  body: PolicyCategoryWrite,
): Promise<PolicyCategoryItem> {
  const response = await apiClient.post(apiEndpoints.policyHierarchy.categories, {
    name: body.name,
    description: body.description ?? null,
  });
  return policyCategoryCreateResponseSchema.parse(response.data).data;
}

export async function createPolicySubCategory(
  body: PolicySubCategoryWrite,
): Promise<PolicySubCategoryItem> {
  const response = await apiClient.post(apiEndpoints.policyHierarchy.subCategories, {
    name: body.name,
    description: body.description ?? null,
    category_id: body.category_id,
  });
  return policySubCategoryCreateResponseSchema.parse(response.data).data;
}
