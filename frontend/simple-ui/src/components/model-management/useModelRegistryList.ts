import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getModelListPage,
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
  const [filters, setFiltersState] = useState<DataTableColumnFilters>({});

  const setFilters = useCallback((next: DataTableColumnFilters) => {
    setFiltersState(next);
    setPage(1);
  }, []);
  const setFilter = useCallback((id: string, value: string) => {
    setFiltersState((current) => {
      const next = { ...current };
      if (value.trim()) next[id] = value;
      else delete next[id];
      return next;
    });
    setPage(1);
  }, []);
  const clearFilters = useCallback(() => setFilters({}), [setFilters]);

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
    queryFn: () => getModelListPage(params),
    // Always stale: every column, search, sort or page change calls the API.
    staleTime: 0,
    enabled,
  });

  return {
    items: (query.data?.items ?? []) as ModelDetails[],
    total: query.data?.total ?? 0,
    isLoading: query.isPending,
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
