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
  const [sortKey, setSortKey] = useState(defaultKey);
  const [sortDirection, setSortDirection] = useState<MeteringSortDirection>(defaultDirection);

  const toggleSort = useCallback((key: string) => {
    setSortKey((prev) => {
      if (prev === key) {
        setSortDirection((d) => (d === "desc" ? "asc" : "desc"));
        return prev;
      }
      setSortDirection("desc");
      return key;
    });
  }, []);

  const sortedRows = useMemo(() => {
    const accessor = accessors[sortKey];
    if (!accessor) return [...rows];
    return sortMeteringRows(rows, accessor, sortDirection);
  }, [rows, sortKey, sortDirection, accessors]);

  return { sortedRows, sortKey, sortDirection, toggleSort };
}

export function sortIndicator(
  active: boolean,
  direction: MeteringSortDirection,
): string {
  if (!active) return "↕";
  return direction === "desc" ? "↓" : "↑";
}
