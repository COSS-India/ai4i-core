import { useQuery } from "@tanstack/react-query";
import {
  fetchApplicationUsageList,
  fetchApplicationUsageSummary,
} from "../services/applicationUsageService";
import { parseError } from "../utils/errorHandler";
import { USAGE_SPEND_STALE_MS } from "../utils/usageSpendHelpers";

interface UseApplicationUsageDataArgs {
  tenantId: string | null;
  refreshNonce: number;
  sortOrder?: "asc" | "desc";
}

export function useApplicationUsageData({
  tenantId,
  refreshNonce,
  sortOrder = "desc",
}: UseApplicationUsageDataArgs) {
  const scopedId = tenantId?.trim() || null;
  const enabled = Boolean(scopedId);

  const summaryQuery = useQuery({
    queryKey: ["usage-applications-summary", scopedId, refreshNonce],
    queryFn: () => {
      if (!scopedId) throw new Error("Institution id is required");
      return fetchApplicationUsageSummary(scopedId);
    },
    enabled,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const listQuery = useQuery({
    queryKey: ["usage-applications", scopedId, sortOrder, refreshNonce],
    queryFn: () => {
      if (!scopedId) throw new Error("Institution id is required");
      return fetchApplicationUsageList({
        tenantId: scopedId,
        sortOrder,
        limit: 500,
        offset: 0,
      });
    },
    enabled,
    staleTime: USAGE_SPEND_STALE_MS,
    retry: 1,
  });

  const errMsg = (e: unknown) => (e ? parseError(e).message : null);

  return {
    isScoped: enabled,
    summary: summaryQuery.data,
    applications: listQuery.data?.data ?? [],
    total: listQuery.data?.total ?? 0,
    summaryError: errMsg(summaryQuery.error),
    listError: errMsg(listQuery.error),
    isSummaryLoading: summaryQuery.isLoading,
    isListLoading: listQuery.isLoading,
    billingPeriod: summaryQuery.data?.billingPeriod ?? "lifetime",
  };
}
