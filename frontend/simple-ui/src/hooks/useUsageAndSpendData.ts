import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchUsageSummary,
  fetchTenantUsageList,
  fetchTenantUsageById,
} from "../services/usageSpendService";
import { fetchTiers } from "../services/tierManagementService";
import { parseError } from "../utils/errorHandler";
import {
  USAGE_SPEND_STALE_MS,
  billingPeriodValue,
  resolveSpendChangePercent,
  summaryFromDetail,
  taskTypeColor,
  type BillingPeriodKey,
} from "../utils/usageSpendHelpers";
import type {
  SpendByTaskType,
  TenantUsageItem,
  UsageSummaryResponse,
} from "../types/usageSpend";

interface UseUsageAndSpendDataArgs {
  scopeTenantId: string | null;
  isTenantView: boolean;
  tenantId: string | null;
  refreshNonce: number;
  periodKey: BillingPeriodKey;
  filterTierId: string;
  filterTaskType: string;
  sortOrder: "asc" | "desc";
  taskTypeNames: string[];
}

export function useUsageAndSpendData({
  scopeTenantId,
  isTenantView,
  tenantId,
  refreshNonce,
  periodKey,
  filterTierId,
  filterTaskType,
  sortOrder,
  taskTypeNames,
}: UseUsageAndSpendDataArgs) {
  const billingPeriod = billingPeriodValue(periodKey);
  const previousBillingPeriod = billingPeriodValue("last");
  const scopedId = (isTenantView ? tenantId : scopeTenantId)?.trim() || null;
  const isScoped = Boolean(scopedId);

  const summaryQuery = useQuery({
    queryKey: ["usage-summary", billingPeriod, refreshNonce],
    queryFn: () => fetchUsageSummary({ billingPeriod }),
    enabled: !isScoped,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const previousSummaryQuery = useQuery({
    queryKey: ["usage-summary", previousBillingPeriod, refreshNonce],
    queryFn: () => fetchUsageSummary({ billingPeriod: previousBillingPeriod }),
    enabled: !isScoped && periodKey === "current",
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const scopedQuery = useQuery({
    queryKey: ["usage-tenant", scopedId, billingPeriod, refreshNonce],
    queryFn: () => {
      if (!scopedId) throw new Error("Tenant id is required");
      return fetchTenantUsageById(scopedId, billingPeriod);
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
      filterTaskType,
      sortOrder,
      refreshNonce,
    ],
    queryFn: () =>
      fetchTenantUsageList({
        billingPeriod,
        tierId: filterTierId || undefined,
        modelTaskType: filterTaskType || undefined,
        sortOrder,
        limit: 100,
        offset: 0,
      }),
    enabled: !isScoped,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const tiersQuery = useQuery({
    queryKey: ["tiers", refreshNonce],
    queryFn: () => fetchTiers(),
    staleTime: 5 * USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const tenants: TenantUsageItem[] = useMemo(() => {
    if (isScoped) return scopedQuery.data ? [scopedQuery.data] : [];
    return tenantsQuery.data?.data ?? [];
  }, [isScoped, scopedQuery.data, tenantsQuery.data?.data]);

  const summaryData: UsageSummaryResponse | undefined = useMemo(() => {
    if (isScoped) return scopedQuery.data ? summaryFromDetail(scopedQuery.data) : undefined;
    const summary = summaryQuery.data;
    if (!summary) return undefined;

    let next: UsageSummaryResponse = summary;
    if (filterTaskType) {
      const spendByModelTaskType = summary.spendByModelTaskType.filter(
        (i) => i.modelTaskType.trim().toLowerCase() === filterTaskType.trim().toLowerCase(),
      );
      const totalSpend = spendByModelTaskType.reduce((s, i) => s + i.spend, 0);
      next = {
        ...summary,
        totalSpend,
        spendByModelTaskType: spendByModelTaskType.map((i) => ({
          ...i,
          percentage: totalSpend > 0 ? Number(((i.spend / totalSpend) * 100).toFixed(1)) : 0,
        })),
      };
    }

    if (next.activeTenants == null || next.budgetExceededTenants == null) {
      const rows = tenantsQuery.data?.data ?? [];
      next = {
        ...next,
        activeTenants: next.activeTenants ?? (tenantsQuery.data?.total ?? rows.length),
        budgetExceededTenants:
          next.budgetExceededTenants ??
          rows.filter((r) => r.budget.percentageUsed > 100 || r.budget.remaining < 0).length,
      };
    }

    return next;
  }, [
    isScoped,
    scopedQuery.data,
    summaryQuery.data,
    filterTaskType,
    tenantsQuery.data?.data,
    tenantsQuery.data?.total,
  ]);

  const spendChangePercent = useMemo(
    () =>
      resolveSpendChangePercent({
        periodKey,
        isScoped,
        apiValue: summaryData?.spendChangePercent ?? summaryQuery.data?.spendChangePercent,
        currentTotal: summaryQuery.data?.totalSpend,
        prevTotal: previousSummaryQuery.data?.totalSpend,
        prevReady:
          previousSummaryQuery.isFetched ||
          !(previousSummaryQuery.isLoading || previousSummaryQuery.isFetching),
      }),
    [
      periodKey,
      isScoped,
      summaryData?.spendChangePercent,
      summaryQuery.data?.spendChangePercent,
      summaryQuery.data?.totalSpend,
      previousSummaryQuery.data?.totalSpend,
      previousSummaryQuery.isFetched,
      previousSummaryQuery.isLoading,
      previousSummaryQuery.isFetching,
    ],
  );

  const taskTypeOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    const add = (t: string) => {
      const n = t.trim();
      if (n && !seen.has(n)) {
        seen.add(n);
        out.push(n);
      }
    };
    taskTypeNames.forEach(add);
    (summaryQuery.data?.spendByModelTaskType ?? []).forEach((i: SpendByTaskType) =>
      add(i.modelTaskType),
    );
    (scopedQuery.data?.tierBreakdown ?? []).forEach((tier) =>
      (tier.taskTypes ?? []).forEach((t) => add(t.taskType)),
    );
    return out;
  }, [taskTypeNames, summaryQuery.data?.spendByModelTaskType, scopedQuery.data?.tierBreakdown]);

  const taskColorByType = useMemo(() => {
    const map = new Map<string, string>();
    taskTypeOptions.forEach((t, i) => map.set(t, taskTypeColor(t, i)));
    return map;
  }, [taskTypeOptions]);

  const errMsg = (e: unknown) => (e ? parseError(e).message : null);

  const hasNoTierAssigned = isScoped && scopedQuery.data?.tierId === "unassigned";

  return {
    billingPeriod,
    isScoped,
    tenants,
    summaryData,
    spendChangePercent,
    taskTypeOptions,
    taskColorByType,
    tiers: tiersQuery.data?.data ?? [],
    hasNoTierAssigned,
    summaryError: isScoped ? errMsg(scopedQuery.error) : errMsg(summaryQuery.error),
    tenantsError: isScoped ? errMsg(scopedQuery.error) : errMsg(tenantsQuery.error),
    isSummaryLoading: isScoped ? scopedQuery.isLoading : summaryQuery.isLoading,
    isTenantsLoading: isScoped ? scopedQuery.isLoading : tenantsQuery.isLoading,
    currency: summaryData?.currency || tenants[0]?.currency || "INR",
  };
}
