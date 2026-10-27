import { Box, type TableCellProps } from "@chakra-ui/react";
import React, { useCallback, useRef } from "react";

/** Default max width for truncated table cells (legacy helpers). */
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

/** Icon / control columns that should stay compact on the right. */
export function isShrinkWrapColumn(col: { id: string; truncate?: boolean }): boolean {
  if (col.truncate === false && /action|activate|deprecate|delete|detail/i.test(col.id)) {
    return true;
  }
  return /^(actions?|activate\/?deprecate|activate|deprecate)$/i.test(col.id);
}

/** Short / metadata columns — never treat as the flex (leftover-width) column. */
function isWeakPrimaryColumn(col: { id: string }): boolean {
  return /^(timestamp|created|created_?at|updated|updated_?at|published|published_?at|published_?on|status|status_?code|task|task_?type|version|method|latency|tier|roles?|permissions?|scope|mode|group|domain|budget|allocation|services?|institutions?|recipient|delivery|channel)$/i.test(
    col.id,
  );
}

/**
 * Column that should absorb leftover width.
 * Prefer long-form fields (name, error, url, …). Never fall back to timestamp/status.
 */
export function resolvePrimaryColumnId(
  columns: readonly { id: string; truncate?: boolean }[],
): string | null {
  const flexPatterns = [
    /^(name|key|key_name|organisation|organization|username|alert|notification|policy|application|tierName|tier_name|pii|piiType|label|title)$/i,
    /^error$/i,
    /^(url|path|message|description|detail|body)$/i,
    /^institution$/i,
  ];
  for (const pattern of flexPatterns) {
    const match = columns.find(
      (column) =>
        pattern.test(column.id) &&
        shouldAutoTruncateColumn(column) &&
        !isShrinkWrapColumn(column),
    );
    if (match) return match.id;
  }
  const firstText = columns.find(
    (column) =>
      shouldAutoTruncateColumn(column) &&
      !isShrinkWrapColumn(column) &&
      !isWeakPrimaryColumn(column),
  );
  return firstText?.id ?? null;
}

export type AdminColumnLayout = {
  w?: TableCellProps["w"];
  minW?: TableCellProps["minW"];
  maxW?: TableCellProps["maxW"];
  whiteSpace?: TableCellProps["whiteSpace"];
};

/** Compact Actions width — fits up to 4 `sm` ghost IconButtons under `table-layout: fixed`. */
export const ADMIN_ACTIONS_COLUMN_WIDTH = "9.75rem";
export const ADMIN_CHEVRON_COLUMN_WIDTH = "2.25rem";

/**
 * Viewport-fit layouts for admin tables (`table-layout: fixed; width: 100%`).
 * - Actions: fixed rem (always visible, no horizontal scroll)
 * - Primary: larger % of remaining width
 * - Others: share the rest equally and truncate
 * Explicit caller widths still win.
 */
export function resolveAdminColumnLayouts(
  columns: readonly {
    id: string;
    truncate?: boolean;
    width?: TableCellProps["w"];
    minWidth?: TableCellProps["minW"];
    maxW?: TableCellProps["maxW"];
  }[],
): Map<string, AdminColumnLayout> {
  const primaryColumnId = resolvePrimaryColumnId(columns);
  const layouts = new Map<string, AdminColumnLayout>();

  const flexColumns: {
    id: string;
    truncate?: boolean;
    width?: TableCellProps["w"];
    minWidth?: TableCellProps["minW"];
    maxW?: TableCellProps["maxW"];
  }[] = [];
  for (const col of columns) {
    if (col.width != null || col.minWidth != null || col.maxW != null) {
      layouts.set(col.id, {
        w: col.width,
        minW: col.minWidth,
        maxW: col.maxW,
        whiteSpace: isShrinkWrapColumn(col) ? "nowrap" : undefined,
      });
      continue;
    }
    if (isShrinkWrapColumn(col)) {
      layouts.set(col.id, {
        w: ADMIN_ACTIONS_COLUMN_WIDTH,
        minW: ADMIN_ACTIONS_COLUMN_WIDTH,
        maxW: ADMIN_ACTIONS_COLUMN_WIDTH,
        whiteSpace: "nowrap",
      });
      continue;
    }
    flexColumns.push(col);
  }

  const flexCount = flexColumns.length;
  if (flexCount === 0) return layouts;

  const hasPrimary =
    primaryColumnId != null && flexColumns.some((column) => column.id === primaryColumnId);
  const otherCount = hasPrimary ? flexCount - 1 : flexCount;
  /*
   * Do NOT assign % widths that sum to 100% — rem Actions / chevron sit outside that
   * budget and would get clipped. Give primary a modest share; leave other flex
   * columns as minW:0 so `table-layout: fixed` distributes leftover space.
   */
  const primaryPct =
    !hasPrimary || flexCount === 1
      ? undefined
      : Math.min(36, Math.max(22, 55 - otherCount * 6));

  for (const col of flexColumns) {
    if (hasPrimary && col.id === primaryColumnId && primaryPct != null) {
      layouts.set(col.id, { w: `${primaryPct}%`, minW: 0 });
    } else {
      layouts.set(col.id, { minW: 0 });
    }
  }

  return layouts;
}

/** @deprecated Prefer resolveAdminColumnLayouts. */
export function resolveAdminColumnLayout(
  col: {
    id: string;
    truncate?: boolean;
    width?: TableCellProps["w"];
    minWidth?: TableCellProps["minW"];
    maxW?: TableCellProps["maxW"];
  },
  primaryColumnId: string | null,
): AdminColumnLayout {
  return (
    resolveAdminColumnLayouts(
      primaryColumnId && col.id !== primaryColumnId
        ? [{ id: primaryColumnId }, col]
        : [col],
    ).get(col.id) ?? { minW: 0 }
  );
}

/** @deprecated Prefer resolveAdminColumnLayouts — kept for existing imports. */
export function adminFixedCellProps(props?: TableCellProps): TableCellProps {
  return props ? { ...props } : {};
}

/** @deprecated Prefer resolveAdminColumnLayouts — kept for existing imports. */
export function adminFixedSize(
  value: TableCellProps["w"] | undefined,
): TableCellProps["w"] | undefined {
  return value;
}

function elementOverflows(node: Element): boolean {
  if (!(node instanceof HTMLElement)) return false;
  return (
    node.scrollWidth > node.clientWidth + 1 ||
    node.scrollHeight > node.clientHeight + 1
  );
}

function treeOverflows(root: HTMLElement): boolean {
  if (elementOverflows(root)) return true;
  const nodes = root.querySelectorAll("*");
  for (let index = 0; index < nodes.length; index += 1) {
    if (elementOverflows(nodes[index])) return true;
  }
  return false;
}

/**
 * Clip overflowing cell content; native `title` tooltip when truncated.
 */
export function TruncatingCellContent({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  const onMouseEnter = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const text = (el.textContent ?? "").trim();
    if (text && treeOverflows(el)) {
      el.setAttribute("title", text);
      return;
    }
    el.removeAttribute("title");
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
          maxWidth: "100%",
        },
      }}
      onMouseEnter={onMouseEnter}
    >
      {children}
    </Box>
  );
}
