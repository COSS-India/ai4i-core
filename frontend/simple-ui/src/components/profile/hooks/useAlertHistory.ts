import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "@chakra-ui/react";
import alertingService from "../../../services/alertingService";
import type { AlertHistoryItem } from "../../../types/alerting";

const PAGE_LIMIT = 20;

export function useAlertHistory(enabled: boolean) {
  const toast = useToast();
  const [items, setItems] = useState<AlertHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
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
          limit: PAGE_LIMIT,
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
    [toast, filterCategory, filterSeverity, dateFrom, dateTo, searchQuery]
  );

  /** Refetch from page 1 with current filters (matches typical “Refresh” behavior). */
  const fetchHistory = useCallback(() => {
    void loadPage(0);
  }, [loadPage]);

  const clearFilters = useCallback(() => {
    setSearchQuery("");
    setFilterSeverity("all");
    setFilterCategory("all");
    setDateFrom("");
    setDateTo("");
    setIsLoading(true);
    void (async () => {
      try {
        const res = await alertingService.listAlertHistory({
          limit: PAGE_LIMIT,
          offset: 0,
        });
        setItems(res.items);
        setTotal(res.total);
        setOffset(0);
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
    })();
  }, [toast]);

  const goPrev = useCallback(() => {
    const next = Math.max(0, offset - PAGE_LIMIT);
    if (next !== offset) void loadPage(next);
  }, [loadPage, offset]);

  const goNext = useCallback(() => {
    const next = offset + PAGE_LIMIT;
    if (next < total) void loadPage(next);
  }, [loadPage, offset, total]);

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

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = offset + items.length;
  const canPrev = offset > 0;
  const canNext = offset + items.length < total;

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
    fetchHistory,
    pageStart,
    pageEnd,
    goPrev,
    goNext,
    canPrev,
    canNext,
    openView,
    closeView,
    isViewOpen,
    viewItem,
  };
}
