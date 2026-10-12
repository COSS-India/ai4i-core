import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  policyCategoryCreateResponseSchema,
  policyCategoryListResponseSchema,
  policyItemResponseSchema,
  policyListResponseSchema,
  policySubCategoryCreateResponseSchema,
  policySubCategoryListResponseSchema,
  policyTypeItemResponseSchema,
  policyTypeListResponseSchema,
  type GuardrailScope,
  type PolicyCategoryItem,
  type PolicyRecord,
  type PolicySubCategoryItem,
  type PolicyTypeItem,
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

export interface PolicyTypeWrite {
  policy_type: string;
  policy_fields: Record<string, unknown>;
}

export async function listPolicyTypes(): Promise<PolicyTypeItem[]> {
  const response = await apiClient.get(apiEndpoints.policyHierarchy.policyTypes);
  return policyTypeListResponseSchema.parse(response.data).data;
}

/** GET /policy-types/{id}. */
export async function getPolicyType(id: number): Promise<PolicyTypeItem> {
  const response = await apiClient.get(apiEndpoints.policyHierarchy.policyTypeById(id));
  return policyTypeItemResponseSchema.parse(response.data).data;
}

export async function createPolicyType(body: PolicyTypeWrite): Promise<PolicyTypeItem> {
  const response = await apiClient.post(apiEndpoints.policyHierarchy.policyTypes, {
    policy_type: body.policy_type,
    policy_fields: body.policy_fields,
  });
  return policyTypeItemResponseSchema.parse(response.data).data;
}

/** PUT /policy-types/{id}. The collection body is policy_fields only. */
export async function updatePolicyType(
  id: number,
  policyFields: Record<string, unknown>,
): Promise<PolicyTypeItem> {
  const response = await apiClient.put(apiEndpoints.policyHierarchy.policyTypeById(id), {
    policy_fields: policyFields,
  });
  return policyTypeItemResponseSchema.parse(response.data).data;
}

export async function deletePolicyType(id: number): Promise<void> {
  await apiClient.delete(apiEndpoints.policyHierarchy.policyTypeById(id));
}

export interface PolicyWrite {
  name: string;
  description?: string | null;
  domain: string[];
  guardrail_scope: GuardrailScope;
  is_global: boolean;
  sub_category_id: number;
  is_active: boolean;
  output_parse_pii: boolean;
  policy_type_id: number[];
}

export interface PolicyPatch {
  description?: string | null;
  domain?: string[];
  guardrail_scope?: GuardrailScope;
  is_global?: boolean;
  is_active?: boolean;
  output_parse_pii?: boolean;
  sub_category_id?: number;
  policy_type_id?: number[];
}

export async function listPolicies(subCategoryId?: number): Promise<PolicyRecord[]> {
  const response = await apiClient.get(apiEndpoints.policyHierarchy.policies, {
    params: subCategoryId == null ? undefined : { sub_category_id: subCategoryId },
  });
  return policyListResponseSchema.parse(response.data).data;
}

export async function createPolicy(body: PolicyWrite): Promise<PolicyRecord> {
  const response = await apiClient.post(apiEndpoints.policyHierarchy.policies, {
    name: body.name,
    description: body.description ?? null,
    domain: body.domain,
    guardrail_scope: body.guardrail_scope,
    is_global: body.is_global,
    sub_category_id: body.sub_category_id,
    is_active: body.is_active,
    output_parse_pii: body.output_parse_pii,
    policy_type_id: body.policy_type_id,
  });
  return policyItemResponseSchema.parse(response.data).data;
}

/** PATCH /policies/{id}. Only supplied fields change. */
export async function updatePolicy(id: number, body: PolicyPatch): Promise<PolicyRecord> {
  const response = await apiClient.patch(apiEndpoints.policyHierarchy.policyById(id), body);
  return policyItemResponseSchema.parse(response.data).data;
}

export async function deletePolicy(id: number): Promise<void> {
  await apiClient.delete(apiEndpoints.policyHierarchy.policyById(id));
}
