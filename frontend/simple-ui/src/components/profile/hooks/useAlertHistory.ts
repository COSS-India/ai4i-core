import { useCallback, useEffect, useMemo, useState } from "react";
import { useToastWithDeduplication } from "../../../utils/toast";
import alertingService from "../../../services/alertingService";
import type { AlertHistoryItem } from "../../../types/alerting";

const DEFAULT_PAGE_SIZE = 25;

export function useAlertHistory(enabled: boolean) {
  const toast = useToastWithDeduplication();
  const [items, setItems] = useState<AlertHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [isLoading, setIsLoading] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [filterSeverity, setFilterSeverity] = useState("all");
  const [filterCategory, setFilterCategory] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [isViewOpen, setIsViewOpen] = useState(false);
  const [viewItem, setViewItem] = useState<AlertHistoryItem | null>(null);

  const hasActiveFilters = useMemo(() => {
    return (
      searchQuery.trim() !== "" ||
      filterSeverity !== "all" ||
      filterCategory !== "all" ||
      dateFrom.trim() !== "" ||
      dateTo.trim() !== ""
    );
  }, [searchQuery, filterSeverity, filterCategory, dateFrom, dateTo]);

  const loadPage = useCallback(
    async (nextOffset: number) => {
      setIsLoading(true);
      try {
        const res = await alertingService.listAlertHistory({
          category: filterCategory !== "all" ? filterCategory : undefined,
          severity: filterSeverity !== "all" ? filterSeverity : undefined,
          date_from: dateFrom.trim() || undefined,
          date_to: dateTo.trim() || undefined,
          search: searchQuery.trim() || undefined,
          limit: pageSize,
          offset: nextOffset,
        });
        setItems(res.items);
        setTotal(res.total);
        setOffset(nextOffset);
      } catch (error) {
        toast({
          title: "Error",
          description: error instanceof Error ? error.message : "Failed to load alert history",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      } finally {
        setIsLoading(false);
      }
    },
    [toast, filterCategory, filterSeverity, dateFrom, dateTo, searchQuery, pageSize]
  );

  const clearFilters = useCallback(() => {
    setSearchQuery("");
    setFilterSeverity("all");
    setFilterCategory("all");
    setDateFrom("");
    setDateTo("");
  }, []);

  const goPrev = useCallback(() => {
    const next = Math.max(0, offset - pageSize);
    if (next !== offset) void loadPage(next);
  }, [loadPage, offset, pageSize]);

  const goNext = useCallback(() => {
    const next = offset + pageSize;
    if (next < total) void loadPage(next);
  }, [loadPage, offset, total, pageSize]);

  const goFirst = useCallback(() => {
    if (offset !== 0) void loadPage(0);
  }, [loadPage, offset]);

  const goLast = useCallback(() => {
    const lastOffset = Math.floor(Math.max(0, total - 1) / pageSize) * pageSize;
    if (lastOffset !== offset) void loadPage(lastOffset);
  }, [loadPage, offset, pageSize, total]);

  const goToPage = useCallback(
    (page: number) => {
      const nextOffset = Math.max(0, (page - 1) * pageSize);
      if (nextOffset !== offset) void loadPage(nextOffset);
    },
    [loadPage, offset, pageSize]
  );

  const openView = useCallback((row: AlertHistoryItem) => {
    setViewItem(row);
    setIsViewOpen(true);
  }, []);

  const closeView = useCallback(() => {
    setIsViewOpen(false);
    setViewItem(null);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void loadPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    void loadPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageSize]);

  useEffect(() => {
    if (!enabled) return;
    void loadPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, filterSeverity, filterCategory, dateFrom, dateTo]);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = offset + items.length;
  const canPrev = offset > 0;
  const canNext = offset + items.length < total;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = total === 0 ? 1 : Math.floor(offset / pageSize) + 1;

  return {
    items,
    total,
    isLoading,
    searchQuery,
    setSearchQuery,
    filterSeverity,
    setFilterSeverity,
    filterCategory,
    setFilterCategory,
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    hasActiveFilters,
    clearFilters,
    pageStart,
    pageEnd,
    pageSize,
    setPageSize,
    currentPage,
    totalPages,
    goPrev,
    goNext,
    goFirst,
    goLast,
    goToPage,
    canPrev,
    canNext,
    openView,
    closeView,
    isViewOpen,
    viewItem,
  };
}
