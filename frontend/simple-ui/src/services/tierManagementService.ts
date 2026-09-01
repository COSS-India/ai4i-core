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
  if (modelTaskType) params.task_types = modelTaskType;
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

/** PATCH /auth/tenants/{tenant_id}/tier — assign or change tier (single endpoint). */
export async function changeTenantTier(
  tenantId: string,
  tierId: string,
): Promise<void> {
  await apiClient.patch(apiEndpoints.tenants.tenantTier(tenantId), {
    tier_id: tierId,
  });
}

export interface TenantTierAssignment {
  tenant_id: string;
  tenant_name?: string;
  tier_id: string;
  tier_name: string;
  allocated_budget: number | string;
  budget_effective_from?: string;
  budget_effective_to?: string;
  updated_at: string;
}

export interface TenantTiersResponse {
  success: boolean;
  data: TenantTierAssignment[];
}

export async function fetchTenantTiers(): Promise<TenantTiersResponse> {
  const response = await apiClient.get(apiEndpoints.tenants.tierList);
  return response.data;
}

export interface AdjustTenantBudgetPayload {
  tenant_id: string;
  action: "top-up" | "top-down";
  amount: number;
}

export interface AdjustTenantBudgetResponse {
  tenant_id: string;
  allocated_budget: number | string;
  applications_recomputed?: number;
  keys_recomputed?: number;
  updated_at: string;
}

export async function adjustTenantBudget(
  payload: AdjustTenantBudgetPayload,
): Promise<AdjustTenantBudgetResponse> {
  const response = await apiClient.patch(
    apiEndpoints.tenants.tenantBudget(payload.tenant_id),
    {
      action: payload.action,
      amount: payload.amount,
    },
  );

  return response.data;
}
