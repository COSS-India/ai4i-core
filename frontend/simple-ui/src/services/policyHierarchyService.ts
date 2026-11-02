import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  policyCategoryCreateResponseSchema,
  policyCategoryListResponseSchema,
  policyCategoryStatusResponseSchema,
  policyCategoryUpdateResponseSchema,
  policyCreateResponseSchema,
  policyItemResponseSchema,
  policyListResponseSchema,
  policySimulationResponseSchema,
  policySubCategoryCreateResponseSchema,
  policySubCategoryListResponseSchema,
  policySubCategoryStatusResponseSchema,
  policySubCategoryUpdateResponseSchema,
  policyTypeCreateResponseSchema,
  policyTypeItemResponseSchema,
  policyTypeListResponseSchema,
  type GuardrailScope,
  type PolicyCategoryItem,
  type PolicyRecord,
  type PolicySimulation,
  type SelectedPolicyFieldRecord,
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

/** PATCH /policies/categories/{id}. Body is `{ name, description }`. */
export async function updatePolicyCategory(
  id: number,
  body: PolicyCategoryWrite,
): Promise<PolicyCategoryItem> {
  const response = await apiClient.patch(apiEndpoints.policyHierarchy.categoryById(id), {
    name: body.name,
    description: body.description ?? null,
  });
  return policyCategoryUpdateResponseSchema.parse(response.data).data;
}

/** DELETE /policies/categories/{id}. 204 when it has no sub-categories. */
export async function deletePolicyCategory(id: number): Promise<void> {
  await apiClient.delete(apiEndpoints.policyHierarchy.categoryById(id));
}

/** PATCH /policies/sub-categories/{id}. Body is `{ name, description }`. */
export async function updatePolicySubCategory(
  id: number,
  body: PolicyCategoryWrite,
): Promise<PolicySubCategoryItem> {
  const response = await apiClient.patch(apiEndpoints.policyHierarchy.subCategoryById(id), {
    name: body.name,
    description: body.description ?? null,
  });
  return policySubCategoryUpdateResponseSchema.parse(response.data).data;
}

/** DELETE /policies/sub-categories/{id}. 204 when no policy references it. */
export async function deletePolicySubCategory(id: number): Promise<void> {
  await apiClient.delete(apiEndpoints.policyHierarchy.subCategoryById(id));
}

/** PATCH /policies/categories/{id}/status. Body is `{ is_active }`. */
export async function updatePolicyCategoryStatus(
  id: number,
  isActive: boolean,
): Promise<PolicyCategoryItem> {
  const response = await apiClient.patch(apiEndpoints.policyHierarchy.categoryStatus(id), {
    is_active: isActive,
  });
  return policyCategoryStatusResponseSchema.parse(response.data).data;
}

/** PATCH /policies/sub-categories/{id}/status. Body is `{ is_active }`. */
export async function updatePolicySubCategoryStatus(
  id: number,
  isActive: boolean,
): Promise<PolicySubCategoryItem> {
  const response = await apiClient.patch(apiEndpoints.policyHierarchy.subCategoryStatus(id), {
    is_active: isActive,
  });
  return policySubCategoryStatusResponseSchema.parse(response.data).data;
}

export interface PolicyTypeWrite {
  policy_type: string;
  policy_fields: Record<string, unknown>;
}

/** GET /policies/policy-types. */
export async function listPolicyTypes(): Promise<PolicyTypeItem[]> {
  const response = await apiClient.get(apiEndpoints.policyHierarchy.policyTypes);
  return policyTypeListResponseSchema.parse(response.data).data.items;
}

/** GET /policies/policy-types/{id}. Create only returns the id, so the row comes from this. */
export async function getPolicyType(id: number): Promise<PolicyTypeItem> {
  const response = await apiClient.get(apiEndpoints.policyHierarchy.policyTypeById(id));
  return policyTypeItemResponseSchema.parse(response.data).data;
}

export async function createPolicyType(body: PolicyTypeWrite): Promise<number> {
  const response = await apiClient.post(apiEndpoints.policyHierarchy.policyTypes, {
    policy_type: body.policy_type,
    policy_fields: body.policy_fields,
  });
  return policyTypeCreateResponseSchema.parse(response.data).data.id;
}

/** PUT /policies/policy-types. policy_type_id is in the body. */
export async function updatePolicyType(
  id: number,
  policyFields: Record<string, unknown>,
): Promise<PolicyTypeItem> {
  const response = await apiClient.put(apiEndpoints.policyHierarchy.policyTypes, {
    policy_type_id: id,
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
  policy_type_id: number[];
  languages?: string[];
  selected_policy_fields?: SelectedPolicyFieldRecord[];
}

export interface PolicyPatch {
  description?: string | null;
  domain?: string[];
  guardrail_scope?: GuardrailScope;
  is_global?: boolean;
  is_active?: boolean;
  sub_category_id?: number;
  policy_type_id?: number[];
  /** Omitted keys keep the stored values. */
  languages?: string[];
  selected_policy_fields?: SelectedPolicyFieldRecord[];
}

const POLICY_PAGE_SIZE = 1000;

export async function listPolicies(subCategoryId?: number): Promise<PolicyRecord[]> {
  const items: PolicyRecord[] = [];
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  while (offset < total) {
    const response = await apiClient.get(apiEndpoints.policyHierarchy.policies, {
      params: {
        offset,
        limit: POLICY_PAGE_SIZE,
        ...(subCategoryId == null ? {} : { sub_category_id: subCategoryId }),
      },
    });
    const page = policyListResponseSchema.parse(response.data);
    items.push(...page.data.items);
    total = page.meta.total;
    if (page.data.items.length === 0) break;
    offset += page.data.items.length;
  }
  return items;
}

/** POST /policies returns policy_id only. */
export async function createPolicy(body: PolicyWrite): Promise<string> {
  const response = await apiClient.post(apiEndpoints.policyHierarchy.policies, {
    name: body.name,
    description: body.description ?? null,
    domain: body.domain,
    guardrail_scope: body.guardrail_scope,
    is_global: body.is_global,
    sub_category_id: body.sub_category_id,
    policy_type_id: body.policy_type_id,
    ...(body.languages ? { languages: body.languages } : {}),
    ...(body.selected_policy_fields ? { selected_policy_fields: body.selected_policy_fields } : {}),
  });
  return policyCreateResponseSchema.parse(response.data).data.policy_id;
}

/** PUT /policies. id is in the body. */
export async function updatePolicy(id: number, body: PolicyPatch): Promise<PolicyRecord> {
  const response = await apiClient.put(apiEndpoints.policyHierarchy.policies, { id, ...body });
  return policyItemResponseSchema.parse(response.data).data;
}

export async function deletePolicy(id: number): Promise<void> {
  await apiClient.delete(apiEndpoints.policyHierarchy.policyById(id));
}

/** POST /pii/simulate on the inference service. policyId is the platform-core policy id. */
export async function simulatePolicy(text: string, policyId: number): Promise<PolicySimulation> {
  const response = await apiClient.post(apiEndpoints.pii.simulate, { text, policyId });
  return policySimulationResponseSchema.parse(response.data);
}
