import { useCallback, useMemo, useState } from "react";

export type TableSortDirection = "asc" | "desc";

/** Controlled sort state for DataTable `sort` / `onSortChange`. */
export type DataTableSortState = {
  key: string;
  direction: TableSortDirection;
};

/**
 * Case-insensitive string compare for name/label columns (admin lists).
 * Intentionally omits `numeric: true` — matches pre-existing Policy/Alerting/PII/API-key name sorts.
 * For metering numeric-aware sort, use {@link sortTableRows} instead.
 */
export function compareLocaleText(
  a: string,
  b: string,
  direction: TableSortDirection,
): number {
  const cmp = a.localeCompare(b, undefined, { sensitivity: "base" });
  return direction === "asc" ? cmp : -cmp;
}

/** Sort rows by a string field; optional stable tie-breaker when names match. */
export function sortRowsByText<T>(
  rows: readonly T[],
  getText: (row: T) => string,
  direction: TableSortDirection,
  tieBreak?: (a: T, b: T) => number,
): T[] {
  return [...rows].sort((a, b) => {
    const cmp = compareLocaleText(getText(a), getText(b), direction);
    if (cmp !== 0) return cmp;
    return tieBreak?.(a, b) ?? 0;
  });
}

/**
 * Registry-style lists: preserve API/time order until the user clicks a sortable
 * column, then sort by that column. Supports multiple column accessors.
 */
export function useDeferredColumnSort(
  defaultKey: string,
  accessors: Record<string, (row: any) => string | number>,
) {
  const [mode, setMode] = useState<"time" | "sorted">("time");
  const [sort, setSort] = useState<DataTableSortState>({
    key: defaultKey,
    direction: "asc",
  });

  const onSortChange = useCallback((next: DataTableSortState) => {
    setMode("sorted");
    setSort(next);
  }, []);

  const apply = useCallback(
    <T,>(rows: readonly T[]): T[] => {
      if (mode === "time") return [...rows];
      const accessor = accessors[sort.key] as ((row: T) => string | number) | undefined;
      if (!accessor) return [...rows];
      return sortTableRows(rows, accessor, sort.direction);
    },
    [mode, sort.key, sort.direction, accessors],
  );

  const displaySort: DataTableSortState = useMemo(
    () =>
      mode === "time"
        ? { key: "", direction: "asc" }
        : sort,
    [mode, sort],
  );

  return useMemo(
    () => ({ mode, sort: displaySort, onSortChange, apply }),
    [mode, displaySort, onSortChange, apply],
  );
}

/**
 * Registry-style lists: preserve API/time order until the user clicks a name column,
 * then sort by name. Keeps the name header visually active (matches prior name-sort UX).
 */
export function useDeferredNameSort(columnKey = "name") {
  const [mode, setMode] = useState<"time" | "name">("time");
  const [direction, setDirection] = useState<TableSortDirection>("asc");

  const sort: DataTableSortState = useMemo(
    () => ({ key: columnKey, direction }),
    [columnKey, direction],
  );

  const onSortChange = useCallback((next: DataTableSortState) => {
    setMode("name");
    setDirection(next.direction);
  }, []);

  const apply = useCallback(
    <T,>(
      rows: readonly T[],
      getName: (row: T) => string,
      options?: {
        tieBreak?: (a: T, b: T) => number;
        /** When mode is `time`, sort with this instead of preserving source order. */
        timeCompare?: (a: T, b: T) => number;
      },
    ): T[] => {
      if (mode === "time") {
        if (options?.timeCompare) return [...rows].sort(options.timeCompare);
        return [...rows];
      }
      return sortRowsByText(rows, getName, direction, options?.tieBreak);
    },
    [mode, direction],
  );

  return useMemo(
    () => ({ mode, direction, sort, onSortChange, apply }),
    [mode, direction, sort, onSortChange, apply],
  );
}

/** Always-on name sort (Alerting, PII, API keys). */
export function useNameColumnSort(columnKey = "name", initial: TableSortDirection = "asc") {
  const [sort, setSort] = useState<DataTableSortState>({
    key: columnKey,
    direction: initial,
  });

  const apply = useCallback(
    <T,>(
      rows: readonly T[],
      getName: (row: T) => string,
      tieBreak?: (a: T, b: T) => number,
    ): T[] => sortRowsByText(rows, getName, sort.direction, tieBreak),
    [sort.direction],
  );

  return useMemo(
    () => ({ sort, onSortChange: setSort, direction: sort.direction, apply }),
    [sort, apply],
  );
}

/**
 * Metering / mixed-type row sort (port of former `sortMeteringRows`).
 * Uses a numeric fast path and `{ numeric: true }` string collation so
 * values like "10 tokens" order naturally. Do not replace with
 * {@link compareLocaleText} — that is for name columns only.
 */
export function sortTableRows<T>(
  rows: readonly T[],
  accessor: (row: T) => string | number,
  direction: TableSortDirection,
): T[] {
  const sorted = [...rows];
  sorted.sort((a, b) => {
    const av = accessor(a);
    const bv = accessor(b);
    if (typeof av === "number" && typeof bv === "number") {
      return direction === "asc" ? av - bv : bv - av;
    }
    const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
    return direction === "asc" ? cmp : -cmp;
  });
  return sorted;
}

export function useTableSort<T>(
  rows: readonly T[],
  defaultKey: string,
  accessors: Record<string, (row: T) => string | number>,
  defaultDirection: TableSortDirection = "desc",
) {
  const [sort, setSort] = useState({
    key: defaultKey,
    direction: defaultDirection,
  });

  const toggleSort = useCallback((key: string) => {
    setSort((prev) => {
      if (prev.key === key) {
        return {
          key,
          direction: (prev.direction === "desc" ? "asc" : "desc") as TableSortDirection,
        };
      }
      return { key, direction: "desc" as TableSortDirection };
    });
  }, []);

  const setSortState = useCallback((next: DataTableSortState) => {
    setSort({ key: next.key, direction: next.direction });
  }, []);

  const sortedRows = useMemo(() => {
    const accessor = accessors[sort.key];
    if (!accessor) return [...rows];
    return sortTableRows(rows, accessor, sort.direction);
  }, [rows, sort.key, sort.direction, accessors]);

  return {
    sortedRows,
    sortKey: sort.key,
    sortDirection: sort.direction,
    toggleSort,
    setSortState,
  };
}
