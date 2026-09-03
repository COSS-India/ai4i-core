import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchUsageSummary,
  fetchTenantUsageList,
  fetchTenantUsageById,
} from "../services/usageSpendService";
import { fetchTiers } from "../services/tierManagementService";
import { parseError } from "../utils/errorHandler";
import { INSTITUTION } from "../config/constants";
import {
  USAGE_SPEND_STALE_MS,
  summaryFromDetail,
} from "../utils/usageSpendHelpers";
import type {
  TenantUsageItem,
  UsageSummaryResponse,
} from "../types/usageSpend";

interface UseUsageAndSpendDataArgs {
  scopeTenantId: string | null;
  isTenantView: boolean;
  tenantId: string | null;
  refreshNonce: number;
  filterTierId: string;
  taskTypeNames: string[];
  billingPeriod: string;
}

export function useUsageAndSpendData({
  scopeTenantId,
  isTenantView,
  tenantId,
  refreshNonce,
  filterTierId,
  taskTypeNames,
  billingPeriod,
}: UseUsageAndSpendDataArgs) {
  const scopedId = (isTenantView ? tenantId : scopeTenantId)?.trim() || null;
  const isScoped = Boolean(scopedId);

  const enabledParam = taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;

  const summaryQuery = useQuery({
    queryKey: ["usage-summary", billingPeriod, filterTierId, enabledParam, refreshNonce],
    queryFn: () =>
      fetchUsageSummary({
        billingPeriod,
        tierId: filterTierId || undefined,
        taskTypes: enabledParam,
      }),
    enabled: !isScoped,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const scopedQuery = useQuery({
    queryKey: ["usage-tenant", scopedId, billingPeriod, enabledParam, refreshNonce],
    queryFn: () => {
      if (!scopedId) throw new Error(`${INSTITUTION} id is required`);
      return fetchTenantUsageById(scopedId, billingPeriod, enabledParam);
    },
    enabled: isScoped,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const tenantsQuery = useQuery({
    queryKey: [
      "usage-tenants",
      billingPeriod,
      filterTierId,
      enabledParam,
      refreshNonce,
    ],
    queryFn: () =>
      fetchTenantUsageList({
        billingPeriod,
        tierId: filterTierId || undefined,
        taskTypes: enabledParam,
        sortOrder: "desc",
        limit: 100,
        offset: 0,
      }),
    enabled: !isScoped,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const tiersQuery = useQuery({
    queryKey: ["tiers", enabledParam, refreshNonce],
    queryFn: () => fetchTiers(enabledParam),
    staleTime: 5 * USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const tenants: TenantUsageItem[] = useMemo(() => {
    if (isScoped) return scopedQuery.data ? [scopedQuery.data] : [];
    return tenantsQuery.data?.data ?? [];
  }, [isScoped, scopedQuery.data, tenantsQuery.data?.data]);

  const summaryData: UsageSummaryResponse | undefined = useMemo(() => {
    if (isScoped) {
      return scopedQuery.data
        ? summaryFromDetail(scopedQuery.data, billingPeriod)
        : undefined;
    }
    const summary = summaryQuery.data;
    if (!summary) return undefined;

    let next: UsageSummaryResponse = summary;

    if (next.activeTenants == null || next.budgetExceededTenants == null) {
      const rows = tenantsQuery.data?.data ?? [];
      next = {
        ...next,
        activeTenants: next.activeTenants ?? (tenantsQuery.data?.total ?? rows.length),
        budgetExceededTenants:
          next.budgetExceededTenants ??
          rows.filter(
            (r) =>
              (r.budget?.percentageUsed ?? 0) > 100 || (r.budget?.remaining ?? 0) < 0,
          ).length,
      };
    }

    return next;
  }, [
    isScoped,
    scopedQuery.data,
    billingPeriod,
    summaryQuery.data,
    tenantsQuery.data?.data,
    tenantsQuery.data?.total,
  ]);

  const errMsg = (e: unknown) => (e ? parseError(e).message : null);

  const hasNoTierAssigned = isScoped && scopedQuery.data?.tierId === "unassigned";

  return {
    billingPeriod,
    isScoped,
    tenants,
    summaryData,
    tiers: tiersQuery.data?.data ?? [],
    hasNoTierAssigned,
    summaryError: isScoped ? errMsg(scopedQuery.error) : errMsg(summaryQuery.error),
    tenantsError: isScoped ? errMsg(scopedQuery.error) : errMsg(tenantsQuery.error),
    isSummaryLoading: isScoped ? scopedQuery.isLoading : summaryQuery.isLoading,
    isTenantsLoading: isScoped ? scopedQuery.isLoading : tenantsQuery.isLoading,
    currency: summaryData?.currency || tenants[0]?.currency || "INR",
  };
}
