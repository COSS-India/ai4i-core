import { useCallback, useEffect, useMemo, useState } from "react";
import { DEFAULT_PAGE_SIZE_OPTIONS, PAGINATION } from "../constants/pagination";

export type UseAdminDataTableOptions = {
  initialPage?: number;
  initialPageSize?: number;
  pageSizeOptions?: readonly number[];
};

export function useAdminDataTable<T>(
  items: T[],
  options: UseAdminDataTableOptions = {}
) {
  const pageSizeOptions = options.pageSizeOptions ?? DEFAULT_PAGE_SIZE_OPTIONS;
  const [page, setPage] = useState(options.initialPage ?? 1);
  const [pageSize, setPageSize] = useState(options.initialPageSize ?? PAGINATION.DEFAULT_TABLE_PAGE_SIZE);

  const totalItems = items.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const startRow = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const endRow = Math.min(page * pageSize, totalItems);

  const paginatedItems = useMemo(
    () => items.slice((page - 1) * pageSize, page * pageSize),
    [items, page, pageSize]
  );

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const resetPage = useCallback(() => setPage(1), []);

  const setPageSizeAndReset = useCallback((size: number) => {
    setPageSize(size);
    setPage(1);
  }, []);

  return {
    paginatedItems,
    page,
    setPage,
    pageSize,
    setPageSize,
    resetPage,
    setPageSizeAndReset,
    totalItems,
    totalPages,
    startRow,
    endRow,
    pageSizeOptions: [...pageSizeOptions],
    canPrev: page > 1,
    canNext: page < totalPages,
  };
}

export type UseAdminDataTableServerOptions = {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  pageSizeOptions?: readonly number[];
};

/** Pagination state owned by parent (e.g. API offset/limit). */
export function useAdminDataTableServer(options: UseAdminDataTableServerOptions) {
  const pageSizeOptions = options.pageSizeOptions ?? DEFAULT_PAGE_SIZE_OPTIONS;
  const { page, pageSize, totalItems } = options;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const startRow = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const endRow = Math.min(page * pageSize, totalItems);

  return {
    page,
    pageSize,
    totalItems,
    totalPages,
    startRow,
    endRow,
    pageSizeOptions: [...pageSizeOptions],
    canPrev: page > 1,
    canNext: page < totalPages,
    setPage: options.onPageChange,
    setPageSizeAndReset: (size: number) => {
      options.onPageSizeChange(size);
      options.onPageChange(1);
    },
    goFirst: () => options.onPageChange(1),
    goPrev: () => options.onPageChange(Math.max(1, page - 1)),
    goNext: () => options.onPageChange(Math.min(totalPages, page + 1)),
    goLast: () => options.onPageChange(totalPages),
  };
}
