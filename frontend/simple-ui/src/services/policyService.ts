import { apiClient } from './api';

const BASE = '/api/v1/policy-engine';

export interface QuotaConfigNested {
  name: string;
  requests_per_hour: number;
  service_limits: Array<{ service_type: string; unit_type: string; limit_value: number }>;
}

export interface RateLimitNested {
  name: string;
  requests_per_hour_per_api_key: number;
  requests_per_hour_per_tenant: number;
}

export interface PlanPolicy {
  id: string;
  plan_name: string;
  cost: number;
  tier: string;
  quota_config: QuotaConfigNested | Record<string, unknown>;
  rate_limit_config: RateLimitNested | Record<string, unknown>;
}

export interface PlanService {
  service_id: string;
  service_name: string;
  unit_type: string;
  cost_per_unit: number;
  tier: string;
}

export async function getPolicies(): Promise<PlanPolicy[]> {
  const { data } = await apiClient.get<PlanPolicy[]>(`${BASE}/policies`);
  return data;
}

export async function createPolicy(payload: {
  plan_name: string;
  cost: number;
  tier: string;
}): Promise<PlanPolicy> {
  const { data } = await apiClient.post<PlanPolicy>(`${BASE}/policies`, payload);
  return data;
}

export async function getPolicyById(id: string): Promise<PlanPolicy> {
  const { data } = await apiClient.get<PlanPolicy>(`${BASE}/policies/${id}`);
  return data;
}

export async function getPolicyByTier(tier: string): Promise<PlanPolicy> {
  const { data } = await apiClient.get<PlanPolicy>(
    `${BASE}/policies/tier/${encodeURIComponent(tier)}`
  );
  return data;
}

export async function updatePolicy(
  id: string,
  payload: Partial<{ plan_name: string; cost: number; tier: string }>
): Promise<PlanPolicy> {
  const { data } = await apiClient.put<PlanPolicy>(`${BASE}/policies/${id}`, payload);
  return data;
}

export async function deletePolicy(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/policies/${id}`);
}

export async function getPoliciesByTenant(tenantId: string): Promise<unknown> {
  const { data } = await apiClient.get(`${BASE}/policies/tenant/${encodeURIComponent(tenantId)}`);
  return data;
}

export async function getPlanServices(planId: string): Promise<PlanService[]> {
  const { data } = await apiClient.get<PlanService[]>(
    `${BASE}/policies/${encodeURIComponent(planId)}/services`
  );
  return data;
}
