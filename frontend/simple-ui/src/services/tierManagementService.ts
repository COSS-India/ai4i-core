import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import type {
  Tier,
  TierStatus,
  TiersListResponse,
  CreateTierPayload,
  UpdateTierPayload,
} from "../types/tierManagement";

export type {
  Tier,
  TierStatus,
  TiersListResponse,
  CreateTierPayload,
  UpdateTierPayload,
  UpdateTierStatusPayload,
} from "../types/tierManagement";

export async function fetchTiers(
  modelTaskType?: string,
  status?: TierStatus,
): Promise<TiersListResponse> {
  const params: Record<string, string> = {};
  if (modelTaskType) params.task_types = modelTaskType;
  if (status) params.status = status;
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

/**
 * PATCH /pay-per-use/tier/{tier_id}/status — single entry point for every
 * lifecycle transition. The backend enforces the allowed edges and answers 400
 * with a `detail` naming the reachable targets when one is not allowed:
 *
 *   INACTIVE    → ACTIVE       (Publish)
 *   ACTIVE      → DEACTIVATED  (Deactivate)
 *   DEACTIVATED → ACTIVE       (Reactivate)
 *   DEACTIVATED → DELETED      (Delete)
 *
 * Returns the full updated tier, so callers can seed the cache from the
 * response instead of refetching.
 */
export async function updateTierStatus(
  tierId: string,
  status: TierStatus,
): Promise<Tier> {
  const response = await apiClient.patch(apiEndpoints.tiers.status(tierId), {
    status,
  });
  return response.data;
}

/**
 * Deletion goes through the status endpoint: `DELETE /pay-per-use/tier` no
 * longer exists server-side, and DELETED is reachable only from DEACTIVATED.
 * The backend answers 409 when the tier is still assigned to a tenant or
 * mapped to a service.
 */
export async function deleteTier(tierId: string): Promise<Tier> {
  return updateTierStatus(tierId, "DELETED");
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
