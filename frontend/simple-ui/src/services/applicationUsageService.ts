import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import type {
  ApplicationUsageDetail,
  ApplicationUsageListParams,
  ApplicationUsageListResponse,
  ApplicationUsageSummary,
} from "../types/applicationUsage";

export type {
  ApplicationUsageDetail,
  ApplicationUsageListItem,
  ApplicationUsageListResponse,
  ApplicationUsageSummary,
  ApiKeyUsageItem,
} from "../types/applicationUsage";

export async function fetchApplicationUsageSummary(
  tenantId: string,
): Promise<ApplicationUsageSummary> {
  const response = await apiClient.get(apiEndpoints.usage.applicationsSummary, {
    params: { tenant_id: tenantId },
  });
  return response.data;
}

export async function fetchApplicationUsageList(
  params: ApplicationUsageListParams,
): Promise<ApplicationUsageListResponse> {
  const query: Record<string, string | number> = { tenant_id: params.tenantId };
  if (params.sortOrder) query.sortOrder = params.sortOrder;
  if (params.limit != null) query.limit = params.limit;
  if (params.offset != null) query.offset = params.offset;
  const response = await apiClient.get(apiEndpoints.usage.applications, { params: query });
  return response.data;
}

export async function fetchApplicationUsageDetail(
  tenantId: string,
  applicationId: number,
): Promise<ApplicationUsageDetail> {
  const response = await apiClient.get(apiEndpoints.usage.application, {
    params: { tenant_id: tenantId, application_id: applicationId },
  });
  return response.data;
}
