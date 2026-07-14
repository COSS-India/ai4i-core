import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import type {
  Tier,
  TiersListResponse,
  CreateTierPayload,
  UpdateTierPayload,
} from "../types/tierManagement";

export type {
  Tier,
  TiersListResponse,
  CreateTierPayload,
  UpdateTierPayload,
} from "../types/tierManagement";

export async function fetchTiers(
  modelTaskType?: string,
): Promise<TiersListResponse> {
  const params: Record<string, string> = {};
  if (modelTaskType) params.modelTaskType = modelTaskType;
  const response = await apiClient.get(apiEndpoints.tiers.list, { params });
  return response.data;
}

export async function createTier(payload: CreateTierPayload): Promise<Tier> {
  const response = await apiClient.post(apiEndpoints.tiers.create, payload);
  return response.data;
}

export async function updateTier(
  tierId: string,
  payload: UpdateTierPayload,
): Promise<Tier> {
  const response = await apiClient.patch(apiEndpoints.tiers.update, {
    tier_id: tierId,
    ...payload,
  });
  return response.data;
}

export async function deleteTier(tierId: string): Promise<void> {
  await apiClient.delete(apiEndpoints.tiers.update, {
    params: { tier_id: tierId },
  });
}

export interface AssignTenantTierPayload {
  tenant_id: string;
  tier_id: string;
  budget: number;
  effective_from: string;
  effective_to: string;
}

export async function assignTenantTier(
  payload: AssignTenantTierPayload,
): Promise<void> {
  await apiClient.post(apiEndpoints.tiers.assignTenant, payload);
}

export interface TenantTierAssignment {
  tenant_id: string;
  tier_id: string;
  tier_name: string;
  budget_limit: string;
  available_balance: string;
  effective_from: string;
  effective_to: string;
  updated_at: string;
}

export interface TenantTiersResponse {
  success: boolean;
  data: TenantTierAssignment[];
}

export async function fetchTenantTiers(): Promise<TenantTiersResponse> {
  const response = await apiClient.get(apiEndpoints.tiers.assignTenant);
  return response.data;
}

export interface ReassignTenantTierPayload {
  tenant_id: string;
  tier_id: string;
}

export async function reassignTenantTier(
  payload: ReassignTenantTierPayload,
): Promise<TenantTierAssignment> {
  const response = await apiClient.patch(
    apiEndpoints.tiers.reassignTenant,
    payload,
  );
  return response.data;
}

export interface AdjustTenantBudgetPayload {
  tenant_id: string;
  action: "top-up" | "top-down";
  amount: number;
}

export interface AdjustTenantBudgetResponse {
  tenant_id: string;
  budget_limit: string;
  available_balance: string;
  updated_at: string;
}

export async function adjustTenantBudget(
  payload: AdjustTenantBudgetPayload,
): Promise<AdjustTenantBudgetResponse> {
  const response = await apiClient.patch(
    apiEndpoints.tiers.adjustBudget,
    payload,
  );

  return response.data;
}
