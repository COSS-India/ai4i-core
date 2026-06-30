import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import type {
  Tier,
  TiersListResponse,
  CreateTierPayload,
  UpdateTierPayload,
} from "../types/tierManagement";

export type { Tier, TiersListResponse, CreateTierPayload, UpdateTierPayload } from "../types/tierManagement";

export async function fetchTiers(modelTaskType?: string): Promise<TiersListResponse> {
  const params: Record<string, string> = {};
  if (modelTaskType) params.modelTaskType = modelTaskType;
  const response = await apiClient.get(apiEndpoints.tiers.list, { params });
  return response.data;
}

export async function getTierById(tierId: string): Promise<Tier> {
  const response = await apiClient.get(apiEndpoints.tiers.tier(tierId));
  return response.data;
}

export async function createTier(payload: CreateTierPayload): Promise<Tier> {
  const response = await apiClient.post(apiEndpoints.tiers.create, payload);
  return response.data;
}

export async function updateTier(tierId: string, payload: UpdateTierPayload): Promise<Tier> {
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

export async function assignTenantTier(payload: AssignTenantTierPayload): Promise<void> {
  await apiClient.post(apiEndpoints.tiers.assignTenant, payload);
}
