import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getModelsPaginated,
  MODEL_LIST_QUERY_KEY,
} from "../../services/modelManagementService";
import type { ModelDetails } from "../../types/platform";
import type { DataTableColumnFilters } from "../common/table";
import { buildModelListParams, modelServerFilters } from "./modelRegistryQuery";

const DEFAULT_MODEL_PAGE_SIZE = 25;

type ModelSort = {
  sort: { key: string; direction: "asc" | "desc" };
  onSortChange: (next: { key: string; direction: "asc" | "desc" }) => void;
};

/**
 * Model List paging, toolbar filters and sort, all done by GET /models/list
 * (like the Services registry). Every change asks the API for one page.
 */
export function useModelRegistryList(options: Readonly<{
  /** `columns=` for the visible columns. */
  columns: string;
  enabledTaskTypes: readonly string[];
  modelSort: ModelSort;
  enabled: boolean;
}>) {
  const { columns, enabledTaskTypes, modelSort, enabled } = options;
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_MODEL_PAGE_SIZE);
  // Toolbar filters keyed by column id (name / status / taskType).
  const [filters, setFilters] = useState<DataTableColumnFilters>({});

  const setFilter = useCallback((id: string, value: string) => {
    setFilters((current) => {
      const next = { ...current };
      if (value.trim()) next[id] = value;
      else delete next[id];
      return next;
    });
    setPage(1);
  }, []);
  const clearFilters = useCallback(() => {
    setFilters({});
    setPage(1);
  }, []);

  const { onSortChange: setSort } = modelSort;
  const onSortChange = useCallback(
    (next: { key: string; direction: "asc" | "desc" }) => {
      setSort(next);
      setPage(1);
    },
    [setSort],
  );
  const onPageSizeChange = useCallback((size: number) => {
    setPageSize(size);
    setPage(1);
  }, []);

  const serverFilterKey = JSON.stringify(modelServerFilters(filters));
  const params = useMemo(
    () =>
      buildModelListParams({
        filters: JSON.parse(serverFilterKey) as DataTableColumnFilters,
        enabledTaskTypes,
        sort: modelSort.sort,
        page,
        pageSize,
        columns,
      }),
    [serverFilterKey, enabledTaskTypes, modelSort.sort, page, pageSize, columns],
  );

  const query = useQuery({
    queryKey: [...MODEL_LIST_QUERY_KEY, params],
    queryFn: () => getModelsPaginated(params),
    // Always stale: every column, search, sort or page change calls the API.
    staleTime: 0,
    enabled,
  });

  // A refetch can return a smaller total (e.g. the only row on the last page
  // was deprecated under Status = Active), leaving `page` past the end and the
  // table showing "No results found". Step back to the last page that has data.
  // Only act on an empty page: when X-Total-Count is unreadable, total falls
  // back to items.length, so a page that still has rows must not be clamped.
  const data = query.data;
  useEffect(() => {
    if (!data || data.items.length > 0 || page <= 1) return;
    const lastPage = Math.max(1, Math.ceil(data.total / pageSize));
    setPage(Math.min(lastPage, page - 1));
  }, [data, page, pageSize]);

  return {
    items: (query.data?.items ?? []) as ModelDetails[],
    total: query.data?.total ?? 0,
    // A retry after an error keeps status "error" until it succeeds, so show the
    // loading state while it is in flight rather than a stale error alert.
    isLoading: query.isPending || (query.isError && query.isFetching),
    // The request suppresses error toasts, so callers must show this themselves;
    // otherwise a failed fetch reads as an empty registry.
    isError: query.isError,
    refetch: query.refetch,
    page,
    pageSize,
    setPage,
    onPageSizeChange,
    filters,
    setFilter,
    clearFilters,
    hasActiveFilters: Object.values(filters).some((value) => value.trim() !== ""),
    onSortChange,
  };
}
