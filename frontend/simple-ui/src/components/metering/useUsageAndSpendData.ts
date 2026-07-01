import { useMemo } from "react";
import { useQuery, useQueries } from "@tanstack/react-query";
import {
  fetchUsageSummary,
  fetchTenantUsageList,
  fetchTenantUsageById,
} from "../../services/usageSpendService";
import { fetchTiers } from "../../services/tierManagementService";
import { parseError } from "../../utils/errorHandler";
import { MODEL_TASK_TYPE_LIST } from "../../config/constants";
import type {
  TenantUsageItem,
  TenantUsageDetail,
  UsageSummaryResponse,
} from "../../types/usageSpend";

interface UseUsageAndSpendDataOptions {
  scopeTenantId?: string | null;
  isTenantView?: boolean;
  tenantId?: string | null;
  refreshNonce?: number;
  filterTier: string;
  filterTaskType: string;
}

function matchesTierFilter(tierName: string, filterTier: string): boolean {
  if (!filterTier) return true;
  return tierName.trim().toLowerCase() === filterTier.trim().toLowerCase();
}

function matchesModelTaskType(value: string, filter: string): boolean {
  if (!filter) return true;
  return value.trim().toLowerCase() === filter.trim().toLowerCase();
}

function applyModelTaskTypeToDetail(
  detail: TenantUsageDetail,
  modelTaskType: string,
): TenantUsageDetail {
  if (!modelTaskType) return detail;
  const breakdown = (detail.breakdown ?? []).filter((item) =>
    matchesModelTaskType(item.modelTaskType, modelTaskType),
  );
  const match = breakdown[0];
  if (!match) {
    return {
      ...detail,
      consumptionToDate: 0,
      remainingQuota: detail.quotaLimit,
      breakdown: [],
    };
  }
  return {
    ...detail,
    consumptionToDate: match.consumptionToDate,
    remainingQuota: match.remainingQuota ?? detail.remainingQuota,
    quotaLimit: match.quotaLimit ?? detail.quotaLimit,
    quotaUnit: match.unit,
    breakdown,
  };
}

function summaryFromTenantDetail(detail: TenantUsageDetail): UsageSummaryResponse {
  const breakdown = detail.breakdown ?? [];
  const spendItems = breakdown.map((item) => ({
    modelTaskType: item.modelTaskType,
    unit: item.unit,
    consumption: item.consumptionToDate,
    spend: item.spend,
    percentage: 0,
  }));
  const breakdownSpend = spendItems.reduce((sum, item) => sum + item.spend, 0);
  const totalSpend = breakdownSpend > 0 ? breakdownSpend : detail.spendToDate;
  return {
    billingPeriod: new Date().toISOString().slice(0, 7),
    totalSpend,
    currency: detail.currency,
    spendByModelTaskType: spendItems.map((item) => ({
      ...item,
      percentage:
        totalSpend > 0 ? Number(((item.spend / totalSpend) * 100).toFixed(1)) : 0,
    })),
  };
}

function detailToListItem(detail: TenantUsageDetail): TenantUsageItem {
  const { breakdown: _breakdown, ...item } = detail;
  return item;
}

function filterTenantList(
  rows: TenantUsageItem[],
  filterTier: string,
): TenantUsageItem[] {
  return rows.filter((row) => matchesTierFilter(row.tier, filterTier));
}

function filterUsageSummary(
  summary: UsageSummaryResponse | undefined,
  filterTaskType: string,
): UsageSummaryResponse | undefined {
  if (!summary || !filterTaskType) return summary;
  const spendByModelTaskType = summary.spendByModelTaskType.filter((item) =>
    matchesModelTaskType(item.modelTaskType, filterTaskType),
  );
  const totalSpend = spendByModelTaskType.reduce((sum, item) => sum + item.spend, 0);
  return {
    ...summary,
    totalSpend,
    spendByModelTaskType: spendByModelTaskType.map((item) => ({
      ...item,
      percentage:
        totalSpend > 0 ? Number(((item.spend / totalSpend) * 100).toFixed(1)) : 0,
    })),
  };
}

function resolveSummaryData(
  isScopedView: boolean,
  scopedTenantDetail: TenantUsageDetail | null,
  summaryQueryData: UsageSummaryResponse | undefined,
  filterTaskType: string,
): UsageSummaryResponse | undefined {
  if (isScopedView) {
    if (!scopedTenantDetail) {
      return undefined;
    }
    return summaryFromTenantDetail(scopedTenantDetail);
  }
  return filterUsageSummary(summaryQueryData, filterTaskType);
}

function resolveErrorMessage(error: unknown): string | null {
  if (!error) {
    return null;
  }
  return parseError(error).message;
}

function resolveScopedTenantId(
  isTenantView: boolean,
  tenantId: string | null | undefined,
  scopeTenantId: string | null | undefined,
): string | null {
  if (isTenantView) {
    return tenantId?.trim() || null;
  }
  return scopeTenantId?.trim() || null;
}

function resolveQueryError(
  isScopedView: boolean,
  scopedQueryError: unknown,
  platformQueryError: unknown,
): string | null {
  if (isScopedView) {
    return resolveErrorMessage(scopedQueryError);
  }
  return resolveErrorMessage(platformQueryError);
}

function resolveIsSummaryLoading(
  isScopedView: boolean,
  scopedLoading: boolean,
  platformLoading: boolean,
): boolean {
  if (isScopedView) {
    return scopedLoading;
  }
  return platformLoading;
}

function resolveIsTenantsLoading(
  isScopedView: boolean,
  filterTaskType: string,
  scopedLoading: boolean,
  tenantsLoading: boolean,
  breakdownLoading: boolean,
): boolean {
  if (isScopedView) {
    return scopedLoading;
  }
  if (filterTaskType) {
    return tenantsLoading || breakdownLoading;
  }
  return tenantsLoading;
}

function resolveEmptyMessage(isScopedView: boolean): string {
  if (isScopedView) {
    return "No usage data available for this tenant.";
  }
  return "No tenant usage data available.";
}

function resolveScopedTenants(
  scopedTenantDetail: TenantUsageDetail | null,
  filterTaskType: string,
): TenantUsageItem[] {
  if (!scopedTenantDetail) return [];
  if (filterTaskType && (scopedTenantDetail.breakdown?.length ?? 0) === 0) {
    return [];
  }
  return [detailToListItem(scopedTenantDetail)];
}

function buildTaskTypeOptions(
  summaryTypes: UsageSummaryResponse["spendByModelTaskType"] | undefined,
  breakdownTypes: TenantUsageDetail["breakdown"] | undefined,
): string[] {
  const seen = new Set<string>();
  const options: string[] = [];
  const addOption = (taskType: string) => {
    const normalized = taskType.trim();
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    options.push(normalized);
  };

  MODEL_TASK_TYPE_LIST.forEach(addOption);
  (summaryTypes ?? []).forEach((item) => addOption(item.modelTaskType));
  (breakdownTypes ?? []).forEach((item) => addOption(item.modelTaskType));
  return options;
}

export function useUsageAndSpendData({
  scopeTenantId = null,
  isTenantView = false,
  tenantId = null,
  refreshNonce = 0,
  filterTier,
  filterTaskType,
}: UseUsageAndSpendDataOptions) {
  const scopedTenantId = resolveScopedTenantId(
    isTenantView,
    tenantId,
    scopeTenantId,
  );
  const isScopedView = Boolean(scopedTenantId);

  const summaryQuery = useQuery({
    queryKey: ["usage-summary", refreshNonce],
    queryFn: () => fetchUsageSummary(),
    enabled: !isScopedView,
    staleTime: 60_000,
    retry: 1,
  });

  const scopedTenantQuery = useQuery({
    queryKey: ["usage-tenant", scopedTenantId, refreshNonce],
    queryFn: () => {
      if (!scopedTenantId) {
        throw new Error("Tenant id is required");
      }
      return fetchTenantUsageById(scopedTenantId);
    },
    enabled: isScopedView && Boolean(scopedTenantId),
    staleTime: 60_000,
    retry: 1,
  });

  const tenantsQuery = useQuery({
    queryKey: ["usage-tenants", refreshNonce],
    queryFn: () => fetchTenantUsageList(),
    enabled: !isScopedView,
    staleTime: 60_000,
    retry: 1,
  });

  const tierFilteredTenantIds = useMemo(() => {
    if (isScopedView || !filterTaskType) return [];
    return (tenantsQuery.data?.data ?? [])
      .filter((row) => matchesTierFilter(row.tier, filterTier))
      .map((row) => row.tenantId);
  }, [isScopedView, filterTaskType, filterTier, tenantsQuery.data?.data]);

  const tenantBreakdownQueries = useQueries({
    queries: tierFilteredTenantIds.map((id) => ({
      queryKey: ["usage-tenant-breakdown", id, refreshNonce],
      queryFn: () => fetchTenantUsageById(id),
      enabled: !isScopedView && Boolean(filterTaskType),
      staleTime: 60_000,
      retry: 1,
    })),
  });

  const tiersQuery = useQuery({
    queryKey: ["tiers", refreshNonce],
    queryFn: () => fetchTiers(),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const scopedTenantDetail = useMemo(() => {
    if (!scopedTenantQuery.data) return null;
    if (!matchesTierFilter(scopedTenantQuery.data.tier, filterTier)) return null;
    return applyModelTaskTypeToDetail(scopedTenantQuery.data, filterTaskType);
  }, [scopedTenantQuery.data, filterTier, filterTaskType]);

  const breakdownFilteredTenants = useMemo(() => {
    if (!filterTaskType) return [];
    return tenantBreakdownQueries
      .map((query) => query.data)
      .filter((detail): detail is TenantUsageDetail => detail != null)
      .map((detail) => applyModelTaskTypeToDetail(detail, filterTaskType))
      .filter((detail) => (detail.breakdown?.length ?? 0) > 0)
      .map(detailToListItem);
  }, [filterTaskType, tenantBreakdownQueries]);

  const tenants = useMemo(() => {
    if (isScopedView) {
      return resolveScopedTenants(scopedTenantDetail, filterTaskType);
    }
    if (filterTaskType) {
      return breakdownFilteredTenants;
    }
    return filterTenantList(tenantsQuery.data?.data ?? [], filterTier);
  }, [
    isScopedView,
    scopedTenantDetail,
    filterTaskType,
    filterTier,
    tenantsQuery.data?.data,
    breakdownFilteredTenants,
  ]);

  const summaryData = resolveSummaryData(
    isScopedView,
    scopedTenantDetail,
    summaryQuery.data,
    filterTaskType,
  );

  const taskTypeOptions = useMemo(
    () =>
      buildTaskTypeOptions(
        summaryQuery.data?.spendByModelTaskType,
        scopedTenantQuery.data?.breakdown,
      ),
    [summaryQuery.data?.spendByModelTaskType, scopedTenantQuery.data?.breakdown],
  );

  const tierNames = tiersQuery.data?.data?.map((tier) => tier.name) ?? [];

  const summaryError = resolveQueryError(
    isScopedView,
    scopedTenantQuery.error,
    summaryQuery.error,
  );

  const tenantsError = resolveQueryError(
    isScopedView,
    scopedTenantQuery.error,
    tenantsQuery.error,
  );

  const isSummaryLoading = resolveIsSummaryLoading(
    isScopedView,
    scopedTenantQuery.isLoading,
    summaryQuery.isLoading,
  );

  const breakdownQueriesLoading = tenantBreakdownQueries.some(
    (query) => query.isLoading,
  );

  const isTenantsLoading = resolveIsTenantsLoading(
    isScopedView,
    filterTaskType,
    scopedTenantQuery.isLoading,
    tenantsQuery.isLoading,
    breakdownQueriesLoading,
  );

  const emptyMessage = resolveEmptyMessage(isScopedView);

  return {
    isScopedView,
    summaryData,
    taskTypeOptions,
    tierNames,
    tenants,
    summaryError,
    tenantsError,
    isSummaryLoading,
    isTenantsLoading,
    emptyMessage,
  };
}
