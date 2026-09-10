import { Box, type BoxProps, type TableCellProps } from "@chakra-ui/react";
import React, { useCallback, useRef } from "react";

/** Default max width for truncated table cells. */
export const DATA_TABLE_CELL_MAX_W = "280px";

/** Bordered scroll shell for rare children-based table markup. Prefer column-driven `DataTable`. */
export function DataTableShell({ children, ...boxProps }: { children: React.ReactNode } & BoxProps) {
  const onMouseOver = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const cell = (e.target as HTMLElement | null)?.closest?.("td, th") as HTMLTableCellElement | null;
    if (!cell) return;
    const overflowed = cell.scrollWidth > cell.clientWidth + 1;
    if (overflowed) {
      const text = (cell.textContent ?? "").trim();
      if (text) cell.setAttribute("title", text);
    } else {
      cell.removeAttribute("title");
    }
  }, []);

  return (
    <Box
      overflowX="auto"
      borderWidth="1px"
      borderColor="gray.200"
      borderRadius="md"
      bg="white"
      onMouseOver={onMouseOver}
      {...boxProps}
    >
      {children}
    </Box>
  );
}

const DEFAULT_TRUNCATE_CELL_PROPS = {
  maxW: DATA_TABLE_CELL_MAX_W,
  overflow: "hidden",
};

export function shouldAutoTruncateColumn(col: { id: string; truncate?: boolean }): boolean {
  if (col.truncate === false) return false;
  if (col.truncate === true) return true;
  if (/^(actions?|delete|detail|tiers|permissions|roles|taskTypes|recipient)$/i.test(col.id)) {
    return false;
  }
  return true;
}

export function getTruncateCellProps(truncate: boolean, maxW?: TableCellProps["maxW"]): TableCellProps {
  if (!truncate) return {};
  return {
    ...DEFAULT_TRUNCATE_CELL_PROPS,
    ...(maxW != null ? { maxW } : {}),
  };
}

/**
 * Clip overflowing cell content; native `title` tooltip when truncated.
 * No Chakra Tooltip wrapper — that was collapsing some cell layouts (e.g. Name).
 */
export function TruncatingCellContent({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  const onMouseEnter = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const overflowed = el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
    if (overflowed) {
      const text = (el.textContent ?? "").trim();
      if (text) el.setAttribute("title", text);
    } else {
      el.removeAttribute("title");
    }
  }, []);

  return (
    <Box ref={ref} minW={0} maxW="100%" overflow="hidden" onMouseEnter={onMouseEnter}>
      {children}
    </Box>
  );
}
