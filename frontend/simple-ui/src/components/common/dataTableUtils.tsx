import { Box, type TableCellProps } from "@chakra-ui/react";
import React, { useCallback, useRef } from "react";

/** Default max width for truncated table cells. */
export const DATA_TABLE_CELL_MAX_W = "280px";

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

const HARD_SIZE_KEYS = ["w", "width", "minW", "maxW", "minWidth", "maxWidth"] as const;

function isHardColumnSize(value: unknown): boolean {
  if (typeof value === "number") return true;
  if (typeof value !== "string") return false;
  return !value.trim().endsWith("%");
}

/**
 * Admin tables use fixed layout and share width equally.
 * Pixel widths are dropped so one long value cannot resize a column.
 * Percentage widths and responsive size objects are kept.
 */
export function adminFixedCellProps(props?: TableCellProps): TableCellProps {
  if (!props) return {};
  const next: TableCellProps = { ...props };
  for (const key of HARD_SIZE_KEYS) {
    if (isHardColumnSize(next[key])) {
      delete next[key];
    }
  }
  return next;
}

export function adminFixedSize(value: TableCellProps["w"] | undefined): TableCellProps["w"] | undefined {
  if (value == null || isHardColumnSize(value)) return undefined;
  return value;
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
    <Box
      ref={ref}
      minW={0}
      maxW="100%"
      overflow="hidden"
      textOverflow="ellipsis"
      whiteSpace="nowrap"
      sx={{
        "& > *": {
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        },
      }}
      onMouseEnter={onMouseEnter}
    >
      {children}
    </Box>
  );
}
