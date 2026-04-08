import { apiClient } from './api';

const BASE = '/api/v1/policy-engine';

export interface QuotaServiceLimitRow {
  service_type: string;
  unit_type: string;
  limit_value: number;
}

export interface QuotaConfig {
  id: string;
  name: string;
  requests_per_hour: number;
  service_limits: QuotaServiceLimitRow[];
}

export async function getQuotaConfigs(): Promise<QuotaConfig[]> {
  const { data } = await apiClient.get<QuotaConfig[]>(`${BASE}/quota-configs`);
  return data;
}

export async function getQuotaConfigByName(name: string): Promise<QuotaConfig> {
  const { data } = await apiClient.get<QuotaConfig>(
    `${BASE}/quota-configs/name/${encodeURIComponent(name)}`
  );
  return data;
}

export async function createQuotaConfig(payload: {
  name: string;
  requests_per_hour: number;
  service_limits: QuotaServiceLimitRow[];
}): Promise<QuotaConfig> {
  const { data } = await apiClient.post<QuotaConfig>(`${BASE}/quota-configs`, payload);
  return data;
}

export async function updateQuotaConfig(
  id: string,
  payload: Partial<{
    name: string;
    requests_per_hour: number;
    service_limits: QuotaServiceLimitRow[];
  }>
): Promise<QuotaConfig> {
  const { data } = await apiClient.put<QuotaConfig>(`${BASE}/quota-configs/${id}`, payload);
  return data;
}

export async function deleteQuotaConfig(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/quota-configs/${id}`);
}
