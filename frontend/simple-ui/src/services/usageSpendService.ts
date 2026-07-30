import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import type {
  UsageSummaryResponse,
  TenantUsageListResponse,
  TenantUsageDetail,
  TenantUsageParams,
  UsageSummaryParams,
} from "../types/usageSpend";

export type {
  UsageSummaryResponse,
  TenantUsageListResponse,
  TenantUsageItem,
  TenantUsageDetail,
} from "../types/usageSpend";

export async function fetchUsageSummary(
  params?: UsageSummaryParams,
): Promise<UsageSummaryResponse> {
  const query: Record<string, string> = {};
  if (params?.billingPeriod) query.billing_period = params.billingPeriod;
  if (params?.taskTypes) query.taskTypes = params.taskTypes;
  const response = await apiClient.get(apiEndpoints.usage.summary, {
    params: query,
  });
  return response.data;
}

export async function fetchTenantUsageList(
  params?: TenantUsageParams,
): Promise<TenantUsageListResponse> {
  const query: Record<string, string | number> = {};
  if (params?.billingPeriod) query.billing_period = params.billingPeriod;
  if (params?.tierId) query.tier_id = params.tierId;
  if (params?.modelTaskType) query.modelTaskType = params.modelTaskType;
  if (params?.taskTypes) query.taskTypes = params.taskTypes;
  if (params?.sortOrder) query.sortOrder = params.sortOrder;
  if (params?.limit != null) query.limit = params.limit;
  if (params?.offset != null) query.offset = params.offset;
  const response = await apiClient.get(apiEndpoints.usage.tenants, { params: query });
  return response.data;
}

export async function fetchTenantUsageById(
  tenantId: string,
  billingPeriod?: string,
  taskTypes?: string,
): Promise<TenantUsageDetail> {
  const query: Record<string, string> = { tenant_id: tenantId };
  if (billingPeriod) query.billing_period = billingPeriod;
  if (taskTypes) query.taskTypes = taskTypes;
  const response = await apiClient.get(apiEndpoints.usage.tenant, {
    params: query,
  });
  return response.data;
}
