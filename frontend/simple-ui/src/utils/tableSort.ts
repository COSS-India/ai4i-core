import { useCallback, useMemo, useState } from "react";

export type TableSortDirection = "asc" | "desc";

/** Controlled sort state for DataTable `sort` / `onSortChange`. */
export type DataTableSortState = {
  key: string;
  direction: TableSortDirection;
};

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
 * Registry-style lists: preserve API/time order until the user clicks a name column,
 * then sort by name. Keeps the name header visually active (matches prior sortControl UX).
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
  };
}

export function tableSortIndicator(active: boolean, direction: TableSortDirection): string {
  if (!active) return "↕";
  return direction === "desc" ? "↓" : "↑";
}
