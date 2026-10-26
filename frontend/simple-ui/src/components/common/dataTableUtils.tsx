import { Box, type TableCellProps } from "@chakra-ui/react";
import React, { useCallback, useRef } from "react";

/** Default max width for truncated table cells (legacy helpers). */
export const DATA_TABLE_CELL_MAX_W = "280px";

const DEFAULT_TRUNCATE_CELL_PROPS = {
  maxW: DATA_TABLE_CELL_MAX_W,
  overflow: "hidden",
};

const NO_AUTO_TRUNCATE_IDS = new Set([
  "action",
  "actions",
  "delete",
  "detail",
  "tiers",
  "permissions",
  "roles",
  "tasktypes",
  "recipient",
]);

const SHRINK_WRAP_IDS = new Set([
  "action",
  "actions",
  "activate",
  "deprecate",
  "activate/deprecate",
  "activatedeprecate",
]);

/** Short / metadata columns — never treat as the flex (leftover-width) column. */
const WEAK_PRIMARY_IDS = new Set([
  "timestamp",
  "created",
  "createdat",
  "created_at",
  "updated",
  "updatedat",
  "updated_at",
  "published",
  "publishedat",
  "published_at",
  "publishedon",
  "published_on",
  "status",
  "statuscode",
  "status_code",
  "task",
  "tasktype",
  "task_type",
  "version",
  "method",
  "latency",
  "tier",
  "role",
  "roles",
  "permission",
  "permissions",
  "scope",
  "mode",
  "group",
  "domain",
  "budget",
  "allocation",
  "service",
  "services",
  "institution",
  "institutions",
  "recipient",
  "delivery",
  "channel",
]);

function normalizeColumnId(id: string): string {
  return id.trim().toLowerCase();
}

function compactColumnId(id: string): string {
  return normalizeColumnId(id).replaceAll("_", "");
}

export function shouldAutoTruncateColumn(col: { id: string; truncate?: boolean }): boolean {
  if (col.truncate === false) return false;
  if (col.truncate === true) return true;
  const id = normalizeColumnId(col.id);
  return !(NO_AUTO_TRUNCATE_IDS.has(id) || NO_AUTO_TRUNCATE_IDS.has(compactColumnId(col.id)));
}

/**
 * Non-truncating columns (actions, toggles) without an explicit width should
 * shrink to their content in `table-layout: fixed` tables. `1%` is the usual
 * hint; content + nowrap then sets the real width from the action count.
 */
export function shrinkToContentWidth(col: {
  id: string;
  truncate?: boolean;
  width?: string;
}): string | undefined {
  if (col.width != null) return col.width;
  if (!shouldAutoTruncateColumn(col)) return "1%";
  return undefined;
}

export function getTruncateCellProps(truncate: boolean, maxW?: TableCellProps["maxW"]): TableCellProps {
  if (!truncate) return {};
  return {
    ...DEFAULT_TRUNCATE_CELL_PROPS,
    ...(maxW != null ? { maxW } : {}),
  };
}

const SHRINK_WRAP_SUBSTRINGS = ["action", "activate", "deprecate", "delete", "detail"] as const;

function idLooksLikeControlColumn(id: string): boolean {
  return SHRINK_WRAP_SUBSTRINGS.some((token) => id.includes(token));
}

/** Icon / control columns that should stay compact on the right. */
export function isShrinkWrapColumn(col: { id: string; truncate?: boolean }): boolean {
  const id = normalizeColumnId(col.id);
  const compact = compactColumnId(col.id);
  if (col.truncate === false && idLooksLikeControlColumn(id)) {
    return true;
  }
  return SHRINK_WRAP_IDS.has(id) || SHRINK_WRAP_IDS.has(compact);
}

function isWeakPrimaryColumn(col: { id: string }): boolean {
  const id = normalizeColumnId(col.id);
  return WEAK_PRIMARY_IDS.has(id) || WEAK_PRIMARY_IDS.has(compactColumnId(col.id));
}

const PRIMARY_FLEX_IDS = [
  new Set([
    "name",
    "key",
    "key_name",
    "keyname",
    "organisation",
    "organization",
    "username",
    "alert",
    "notification",
    "policy",
    "application",
    "tiername",
    "tier_name",
    "pii",
    "piitype",
    "label",
    "title",
  ]),
  new Set(["error"]),
  new Set(["url", "path", "message", "description", "detail", "body"]),
  new Set(["institution"]),
];

/**
 * Column that should absorb leftover width.
 * Prefer long-form fields (name, error, url, …). Never fall back to timestamp/status.
 */
export function resolvePrimaryColumnId(
  columns: readonly { id: string; truncate?: boolean }[],
): string | null {
  for (const idSet of PRIMARY_FLEX_IDS) {
    const match = columns.find((column) => {
      const id = normalizeColumnId(column.id);
      const compact = compactColumnId(column.id);
      return (
        (idSet.has(id) || idSet.has(compact)) &&
        shouldAutoTruncateColumn(column) &&
        !isShrinkWrapColumn(column)
      );
    });
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

type AdminColumnInput = {
  id: string;
  truncate?: boolean;
  width?: TableCellProps["w"];
  minWidth?: TableCellProps["minW"];
  maxW?: TableCellProps["maxW"];
};

function primaryFlexPercent(otherCount: number): number {
  return Math.min(36, Math.max(22, 55 - otherCount * 6));
}

function hasExplicitColumnWidth(col: AdminColumnInput): boolean {
  return col.width != null || col.minWidth != null || col.maxW != null;
}

function explicitColumnLayout(col: AdminColumnInput): AdminColumnLayout {
  return {
    w: col.width,
    minW: col.minWidth,
    maxW: col.maxW,
    whiteSpace: isShrinkWrapColumn(col) ? "nowrap" : undefined,
  };
}

function actionsColumnLayout(): AdminColumnLayout {
  return {
    w: ADMIN_ACTIONS_COLUMN_WIDTH,
    minW: ADMIN_ACTIONS_COLUMN_WIDTH,
    maxW: ADMIN_ACTIONS_COLUMN_WIDTH,
    whiteSpace: "nowrap",
  };
}

function partitionAdminColumns(columns: readonly AdminColumnInput[]): {
  layouts: Map<string, AdminColumnLayout>;
  flexColumns: AdminColumnInput[];
} {
  const layouts = new Map<string, AdminColumnLayout>();
  const flexColumns: AdminColumnInput[] = [];
  for (const col of columns) {
    if (hasExplicitColumnWidth(col)) {
      layouts.set(col.id, explicitColumnLayout(col));
      continue;
    }
    if (isShrinkWrapColumn(col)) {
      layouts.set(col.id, actionsColumnLayout());
      continue;
    }
    flexColumns.push(col);
  }
  return { layouts, flexColumns };
}

function applyFlexColumnLayouts(
  layouts: Map<string, AdminColumnLayout>,
  flexColumns: AdminColumnInput[],
  primaryColumnId: string | null,
): void {
  const flexCount = flexColumns.length;
  if (flexCount === 0) return;

  const hasPrimary =
    primaryColumnId != null && flexColumns.some((column) => column.id === primaryColumnId);
  /*
   * Do NOT assign % widths that sum to 100% — rem Actions / chevron sit outside that
   * budget and would get clipped. Give primary a modest share; leave other flex
   * columns as minW:0 so `table-layout: fixed` distributes leftover space.
   */
  let primaryPct: number | undefined;
  if (hasPrimary && flexCount > 1) {
    primaryPct = primaryFlexPercent(flexCount - 1);
  }

  for (const col of flexColumns) {
    if (hasPrimary && col.id === primaryColumnId && primaryPct != null) {
      layouts.set(col.id, { w: `${primaryPct}%`, minW: 0 });
      continue;
    }
    layouts.set(col.id, { minW: 0 });
  }
}

/**
 * Viewport-fit layouts for admin tables (`table-layout: fixed; width: 100%`).
 * - Actions: fixed rem (always visible, no horizontal scroll)
 * - Primary: larger % of remaining width
 * - Others: share the rest equally and truncate
 * Explicit caller widths still win.
 */
export function resolveAdminColumnLayouts(
  columns: readonly AdminColumnInput[],
): Map<string, AdminColumnLayout> {
  const primaryColumnId = resolvePrimaryColumnId(columns);
  const { layouts, flexColumns } = partitionAdminColumns(columns);
  applyFlexColumnLayouts(layouts, flexColumns, primaryColumnId);
  return layouts;
}

/** @deprecated Prefer resolveAdminColumnLayouts. */
export function resolveAdminColumnLayout(
  col: AdminColumnInput,
  primaryColumnId: string | null,
): AdminColumnLayout {
  const columns: AdminColumnInput[] =
    primaryColumnId && col.id !== primaryColumnId
      ? [{ id: primaryColumnId }, col]
      : [col];
  return resolveAdminColumnLayouts(columns).get(col.id) ?? { minW: 0 };
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
  for (const node of Array.from(root.querySelectorAll("*"))) {
    if (elementOverflows(node)) return true;
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
