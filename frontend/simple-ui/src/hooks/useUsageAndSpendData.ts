import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchTenantUsageList,
  fetchTenantUsageById,
} from "../services/usageSpendService";
import { fetchTiers } from "../services/tierManagementService";
import { parseError } from "../utils/errorHandler";
import { INSTITUTION } from "../config/constants";
import { USAGE_SPEND_STALE_MS } from "../utils/usageSpendHelpers";
import { retryUnlessInvalidPeriod } from "../utils/meteringQuery";
import { periodQueryKeyParts } from "../utils/meteringDateRange";
import type { MeteringPeriod } from "../types/metering";
import type { TenantUsageItem } from "../types/usageSpend";

interface UseUsageAndSpendDataArgs {
  scopeTenantId: string | null;
  isTenantView: boolean;
  period: MeteringPeriod;
  tenantId: string | null;
  refreshNonce: number;
  filterTierId: string;
  taskTypeNames: string[];
}

export function useUsageAndSpendData({
  scopeTenantId,
  isTenantView,
  period,
  tenantId,
  refreshNonce,
  filterTierId,
  taskTypeNames,
}: UseUsageAndSpendDataArgs) {
  const scopedId = (isTenantView ? tenantId : scopeTenantId)?.trim() || null;
  const isScoped = Boolean(scopedId);

  const enabledParam = taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;

  const scopedQuery = useQuery({
    queryKey: ["usage-tenant", scopedId, ...periodQueryKeyParts(period), enabledParam, refreshNonce],
    queryFn: () => {
      if (!scopedId) throw new Error(`${INSTITUTION} id is required`);
      return fetchTenantUsageById(scopedId, period, enabledParam);
    },
    enabled: isScoped,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: retryUnlessInvalidPeriod,
  });

  const tenantsQuery = useQuery({
    queryKey: ["usage-tenants", ...periodQueryKeyParts(period), filterTierId, enabledParam, refreshNonce],
    queryFn: () =>
      fetchTenantUsageList({
        period,
        tierId: filterTierId || undefined,
        taskTypes: enabledParam,
        sortOrder: "desc",
        limit: 100,
        offset: 0,
      }),
    enabled: !isScoped,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: retryUnlessInvalidPeriod,
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

  const errMsg = (e: unknown) => (e ? parseError(e).message : null);

  const hasNoTierAssigned = isScoped && scopedQuery.data?.tierId === "unassigned";

  return {
    isScoped,
    tenants,
    tiers: tiersQuery.data?.data ?? [],
    hasNoTierAssigned,
    tenantsError: isScoped ? errMsg(scopedQuery.error) : errMsg(tenantsQuery.error),
    isTenantsLoading: isScoped ? scopedQuery.isLoading : tenantsQuery.isLoading,
  };
}
