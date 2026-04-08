import { apiClient } from './api';

const BASE = '/api/v1/pay-per-use';

export interface AdopterUsageSummary {
  total_requests_today: number;
  requests_vs_yesterday_percent: number;
  active_tenants: number;
  plan_breakdown: { premium: number; standard: number; basic: number };
  cost_consumed_this_month: number;
  blocked_requests: {
    total: number;
    quota_exceeded: number;
    rate_limited: number;
  };
}

export interface AdopterServiceUsageRow {
  service_name: string;
  unit_type: string;
  used: number;
  limit: number;
}

export interface AdopterTopTenantRow {
  tenant_id: string;
  tenant_name: string;
  plan: string;
  cost: number;
  status: string;
}

export interface AdopterUsageResponse {
  summary: AdopterUsageSummary;
  service_usage: AdopterServiceUsageRow[];
  top_tenants: AdopterTopTenantRow[];
}

export interface TenantPlanSummary {
  plan_name: string;
  tier: string;
  cost: number;
}

export interface TenantWalletSummary {
  total_plan_cost: number;
  total_used: number;
  remaining: number;
  utilization_percent: number;
}

export interface TenantServiceUsageRow {
  service_name: string;
  unit_type: string;
  units_used: number;
  quota_limit: number;
  quota_percent: number;
  rate_per_unit: number;
  total_cost: number;
}

export interface TenantApiKeyRow {
  api_key_id: string;
  api_key_masked: string;
  requests: number;
  units_consumed: number;
  total_cost: number;
  last_used: string | null;
}

export interface TenantUsageAlerts {
  quota_warning: boolean;
  quota_exceeded: boolean;
  budget_low: boolean;
  budget_exhausted: boolean;
}

export interface TenantUsageDetailResponse {
  tenant_id: string;
  tenant_name: string;
  plan: TenantPlanSummary;
  wallet: TenantWalletSummary;
  status: string;
  total_requests: number;
  service_usage: TenantServiceUsageRow[];
  api_key_breakdown: TenantApiKeyRow[];
  alerts: TenantUsageAlerts;
}

export async function getAdopterUsage(): Promise<AdopterUsageResponse> {
  const { data } = await apiClient.get<AdopterUsageResponse>(`${BASE}/usage/adopter`);
  return data;
}

export async function getTenantUsage(tenantId: string): Promise<TenantUsageDetailResponse> {
  const { data } = await apiClient.get<TenantUsageDetailResponse>(
    `${BASE}/usage/tenant/${encodeURIComponent(tenantId)}`
  );
  return data;
}

export async function getWalletBalance(tenantId: string): Promise<{
  balance: number;
  currency: string;
  total_plan_cost?: number;
  total_used?: number;
  remaining?: number;
}> {
  const { data } = await apiClient.get(`${BASE}/wallet/${encodeURIComponent(tenantId)}`);
  return data;
}

export async function topUpWallet(tenantId: string, amount: number): Promise<unknown> {
  const { data } = await apiClient.post(`${BASE}/wallet/${encodeURIComponent(tenantId)}/topup`, { amount });
  return data;
}

export async function getQuotaStatus(tenantId: string): Promise<unknown> {
  const { data } = await apiClient.get(`${BASE}/quota/${encodeURIComponent(tenantId)}/status`);
  return data;
}
