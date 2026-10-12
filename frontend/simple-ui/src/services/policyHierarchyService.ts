import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  policyCategoryListResponseSchema,
  policySubCategoryListResponseSchema,
  type PolicyCategoryItem,
  type PolicySubCategoryItem,
} from "./dto/schemas/policyHierarchy";

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
