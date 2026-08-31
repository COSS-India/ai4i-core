import { useCallback, useMemo, useState } from "react";

export type MeteringSortDirection = "asc" | "desc";

export function sortMeteringRows<T>(
  rows: readonly T[],
  accessor: (row: T) => string | number,
  direction: MeteringSortDirection,
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

export function useMeteringTableSort<T>(
  rows: readonly T[],
  defaultKey: string,
  accessors: Record<string, (row: T) => string | number>,
  defaultDirection: MeteringSortDirection = "desc",
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
          direction: prev.direction === "desc" ? "asc" : "desc",
        };
      }
      return { key, direction: "desc" as MeteringSortDirection };
    });
  }, []);

  const sortedRows = useMemo(() => {
    const accessor = accessors[sort.key];
    if (!accessor) return [...rows];
    return sortMeteringRows(rows, accessor, sort.direction);
  }, [rows, sort.key, sort.direction, accessors]);

  return {
    sortedRows,
    sortKey: sort.key,
    sortDirection: sort.direction,
    toggleSort,
  };
}

export function sortIndicator(
  active: boolean,
  direction: MeteringSortDirection,
): string {
  if (!active) return "↕";
  return direction === "desc" ? "↓" : "↑";
}
