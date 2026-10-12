import apiClient from "./api";
import { apiEndpoints } from "./apiEndpoints";
import { buildPeriodParams } from "../utils/meteringDateRange";
import type { MeteringPeriod } from "../types/metering";
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

/** `period` query params, or none — callers outside the Usage Dashboard read only lifetime figures. */
function periodParams(period?: MeteringPeriod): Record<string, string> {
  return period ? buildPeriodParams(period) : {};
}

export async function fetchApplicationUsageSummary(
  tenantId: string,
  period?: MeteringPeriod,
): Promise<ApplicationUsageSummary> {
  const response = await apiClient.get(apiEndpoints.usage.applicationsSummary, {
    params: { tenant_id: tenantId, ...periodParams(period) },
  });
  return response.data;
}

export async function fetchApplicationUsageList(
  params: ApplicationUsageListParams,
): Promise<ApplicationUsageListResponse> {
  const query: Record<string, string | number> = {
    tenant_id: params.tenantId,
    ...periodParams(params.period),
  };
  if (params.sortOrder) query.sortOrder = params.sortOrder;
  if (params.limit != null) query.limit = params.limit;
  if (params.offset != null) query.offset = params.offset;
  const response = await apiClient.get(apiEndpoints.usage.applications, { params: query });
  return response.data;
}

export async function fetchApplicationUsageDetail(
  tenantId: string,
  applicationId: number,
  period?: MeteringPeriod,
): Promise<ApplicationUsageDetail> {
  const response = await apiClient.get(apiEndpoints.usage.application, {
    params: { tenant_id: tenantId, application_id: applicationId, ...periodParams(period) },
  });
  return response.data;
}
