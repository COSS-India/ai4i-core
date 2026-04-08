import { apiClient } from './api';

const BASE = '/api/v1/policy-engine';

export interface RateLimitConfig {
  id: string;
  name: string;
  requests_per_hour_per_api_key: number;
  requests_per_hour_per_tenant: number;
}

export async function getRateLimitConfigs(): Promise<RateLimitConfig[]> {
  const { data } = await apiClient.get<RateLimitConfig[]>(`${BASE}/rate-limit-configs`);
  return data;
}

export async function getRateLimitConfigByName(name: string): Promise<RateLimitConfig> {
  const { data } = await apiClient.get<RateLimitConfig>(
    `${BASE}/rate-limit-configs/name/${encodeURIComponent(name)}`
  );
  return data;
}

export async function createRateLimitConfig(payload: {
  name: string;
  requests_per_hour_per_api_key: number;
  requests_per_hour_per_tenant: number;
}): Promise<RateLimitConfig> {
  const { data } = await apiClient.post<RateLimitConfig>(`${BASE}/rate-limit-configs`, payload);
  return data;
}

export async function updateRateLimitConfig(
  id: string,
  payload: Partial<{
    name: string;
    requests_per_hour_per_api_key: number;
    requests_per_hour_per_tenant: number;
  }>
): Promise<RateLimitConfig> {
  const { data } = await apiClient.put<RateLimitConfig>(`${BASE}/rate-limit-configs/${id}`, payload);
  return data;
}

export async function deleteRateLimitConfig(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/rate-limit-configs/${id}`);
}
