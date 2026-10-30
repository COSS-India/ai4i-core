import {
  Badge,
  Box,
  type BadgeProps,
  type TableCellProps,
} from "@chakra-ui/react";
import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

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
  "modeltasktype",
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
  "application",
]);

/** Compact rem pins for badge / icon / code columns (`table-layout: fixed`). */
const COMPACT_COLUMN_WIDTHS: Record<string, string> = {
  status: "8.5rem",
  level: "6.5rem",
  timestamp: "11.5rem",
  createdat: "11.5rem",
  created_at: "11.5rem",
  created: "7.5rem",
  version: "5.5rem",
  task: "5.75rem",
  modeltasktype: "5.75rem",
  tasktype: "7.75rem",
  task_type: "7.75rem",
  method: "5.25rem",
  statuscode: "6.75rem",
  status_code: "6.75rem",
  servicecount: "7.5rem",
  services: "6.5rem",
  institutions: "7rem",
};

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

/** `1%` hint for non-truncating columns so content + nowrap sets the real width. */
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

function compactColumnWidth(col: { id: string }): string | undefined {
  const id = normalizeColumnId(col.id);
  return COMPACT_COLUMN_WIDTHS[id] ?? COMPACT_COLUMN_WIDTHS[compactColumnId(col.id)];
}

function isCompactColumn(col: { id: string }): boolean {
  return compactColumnWidth(col) != null;
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

/** Prefer long-form fields (name, error, url) for leftover width; never timestamp/status. */
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

export const ADMIN_ACTIONS_COLUMN_WIDTH = "9.75rem";
export const ADMIN_CHEVRON_COLUMN_WIDTH = "2.25rem";

type AdminColumnInput = {
  id: string;
  truncate?: boolean;
  width?: TableCellProps["w"];
  minWidth?: TableCellProps["minW"];
  maxW?: TableCellProps["maxW"];
};

/** `1%` / auto are shrink-wrap hints, not real pins under `table-layout: fixed`. */
function isFluidWidthHint(value: TableCellProps["w"] | TableCellProps["minW"]): boolean {
  if (value == null) return true;
  if (typeof value !== "string") return false;
  const v = value.trim().toLowerCase();
  return v === "1%" || v === "auto" || v === "min-content" || v === "max-content";
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

function pinnedControlColumnLayout(col: AdminColumnInput): AdminColumnLayout {
  const candidate = col.width ?? col.minWidth ?? col.maxW;
  if (candidate != null && !isFluidWidthHint(candidate)) {
    const pinned = col.maxW ?? col.width ?? col.minWidth ?? candidate;
    return {
      w: col.width ?? pinned,
      minW: col.minWidth ?? pinned,
      maxW: pinned,
      whiteSpace: "nowrap",
    };
  }
  return actionsColumnLayout();
}

function partitionAdminColumns(columns: readonly AdminColumnInput[]): {
  layouts: Map<string, AdminColumnLayout>;
  flexColumns: AdminColumnInput[];
} {
  const layouts = new Map<string, AdminColumnLayout>();
  const flexColumns: AdminColumnInput[] = [];
  for (const col of columns) {
    if (isShrinkWrapColumn(col)) {
      layouts.set(col.id, pinnedControlColumnLayout(col));
      continue;
    }
    if (col.width != null && !isFluidWidthHint(col.width)) {
      layouts.set(col.id, explicitColumnLayout(col));
      continue;
    }
    flexColumns.push(col);
  }
  return { layouts, flexColumns };
}

function applyFlexColumnLayouts(
  layouts: Map<string, AdminColumnLayout>,
  flexColumns: AdminColumnInput[],
): void {
  for (const col of flexColumns) {
    layouts.set(col.id, { minW: 0 });
  }
}

/** Viewport-fit layouts for admin tables (`table-layout: fixed`). */
export function resolveAdminColumnLayouts(
  columns: readonly AdminColumnInput[],
): Map<string, AdminColumnLayout> {
  const { layouts, flexColumns } = partitionAdminColumns(columns);
  applyFlexColumnLayouts(layouts, flexColumns);
  return layouts;
}

export type ColumnSizingMode = "fixed" | "content" | "shrink";

export type ColumnSizingInput = {
  natural: number;
  header: number;
  mode: ColumnSizingMode;
  minPx?: number;
};

const MIN_SHRINK_COLUMN_PX = 96;

export function resolveColumnSizingMode(col: AdminColumnInput): ColumnSizingMode {
  if (isShrinkWrapColumn(col)) return "fixed";
  if (col.width != null && !isFluidWidthHint(col.width)) return "fixed";
  return "shrink";
}

/** Pinned rem width for compact columns; used when mode is fixed. */
export function resolveFixedColumnWidthPx(col: AdminColumnInput): number | undefined {
  return (
    cssLengthToPx(col.width) ??
    cssLengthToPx(compactColumnWidth(col)) ??
    cssLengthToPx(col.maxW)
  );
}

/** px for `"12px"` / `"9rem"` / numbers; undefined for %, auto and responsive objects. */
export function cssLengthToPx(value: unknown): number | undefined {
  if (typeof value === "number") return value;
  if (typeof value !== "string") return undefined;
  const v = value.trim().toLowerCase();
  const n = Number.parseFloat(v);
  if (Number.isNaN(n)) return undefined;
  if (v.endsWith("px")) return n;
  if (v.endsWith("rem") || v.endsWith("em")) return n * 16;
  return undefined;
}

function shrinkFloor(col: ColumnSizingInput): number {
  if (col.mode !== "shrink") return col.natural;
  return Math.min(col.natural, col.minPx ?? MIN_SHRINK_COLUMN_PX);
}

function shrinkableIndexes(cols: readonly ColumnSizingInput[]): number[] {
  return cols
    .map((c, i) => (c.mode === "shrink" ? i : -1))
    .filter((i) => i >= 0);
}

function growShrinkColumns(
  widths: number[],
  _cols: readonly ColumnSizingInput[],
  shrinkable: readonly number[],
  available: number,
  total: number,
): number[] {
  const next = widths.map((w) => Math.floor(w));
  const targets = shrinkable.length > 0 ? shrinkable : [0];
  let remaining = Math.max(0, available - total);
  const share = Math.floor(remaining / targets.length);
  for (const i of targets) {
    next[i] += share;
  }
  remaining = available - next.reduce((sum, w) => sum + w, 0);
  for (let n = 0; remaining > 0; n += 1, remaining -= 1) {
    next[targets[n % targets.length]] += 1;
  }
  return next;
}

/** Binary-search a shared max width so shrink columns fit the leftover budget. */
function shrinkLevelForBudget(
  cols: readonly ColumnSizingInput[],
  shrinkable: readonly number[],
  floors: readonly number[],
  budget: number,
): number {
  const widthAt = (level: number) =>
    shrinkable.reduce(
      (sum, i) => sum + Math.max(floors[i], Math.min(cols[i].natural, level)),
      0,
    );
  if (budget <= 0 || widthAt(0) >= budget) return 0;

  let lo = 0;
  let hi = Math.max(...shrinkable.map((i) => cols[i].natural), 0);
  for (let step = 0; step < 24; step++) {
    const mid = (lo + hi) / 2;
    if (widthAt(mid) <= budget) lo = mid;
    else hi = mid;
  }
  return lo;
}

function fitWidthsToAvailable(widths: number[], available: number): number[] {
  const assigned = widths.reduce((sum, w) => sum + w, 0);
  if (assigned <= 0) return widths.map(() => 0);
  if (assigned <= available) {
    return widths.map((w) => Math.round(w));
  }
  const scale = available / assigned;
  return widths.map((w) => Math.max(1, Math.floor(w * scale)));
}

/** Fit column widths to the viewport without horizontal scroll. */
export function distributeColumnWidths(
  cols: readonly ColumnSizingInput[],
  available: number,
): number[] {
  const widths = cols.map((c) => c.natural);
  if (available <= 0) return widths;
  const total = widths.reduce((sum, w) => sum + w, 0);
  const shrinkable = shrinkableIndexes(cols);

  if (total <= available) {
    return growShrinkColumns(widths, cols, shrinkable, available, total);
  }

  const locked = cols.reduce(
    (sum, c) => (c.mode === "shrink" ? sum : sum + c.natural),
    0,
  );
  const floors = cols.map(shrinkFloor);
  const level = shrinkLevelForBudget(
    cols,
    shrinkable,
    floors,
    available - locked,
  );
  for (const i of shrinkable) {
    widths[i] = Math.max(floors[i], Math.min(cols[i].natural, level));
  }
  return fitWidthsToAvailable(widths, available);
}

/** Natural single-line widths from offscreen clones; `visible` skips `display: none` cols. */
export function measureColumnNaturalWidths(
  table: HTMLTableElement,
  columnCount: number,
): { header: number[]; natural: number[]; visible: boolean[] } | null {
  const headRow = table.tHead?.rows[0];
  if (headRow?.cells.length == null || headRow.cells.length < columnCount) {
    return null;
  }
  const visible = Array.from(
    { length: columnCount },
    (_, i) => getComputedStyle(headRow.cells[i]).display !== "none",
  );
  const bodyRows = Array.from(table.tBodies[0]?.rows ?? []).filter(
    (row) =>
      row.cells.length >= columnCount &&
      Array.from(row.cells).every((cell) => cell.colSpan === 1),
  );

  const sandbox = document.createElement("div");
  sandbox.setAttribute("aria-hidden", "true");
  Object.assign(sandbox.style, {
    position: "absolute",
    top: "0",
    left: "-100000px",
    visibility: "hidden",
    pointerEvents: "none",
  });
  const clones = [headRow, ...bodyRows].map((row) =>
    Array.from({ length: columnCount }, (_, i) => {
      const clone = row.cells[i].cloneNode(true) as HTMLElement;
      Object.assign(clone.style, {
        display: "block",
        width: "max-content",
        minWidth: "0",
        maxWidth: "none",
        overflow: "visible",
      });
      sandbox.appendChild(clone);
      return clone;
    }),
  );

  document.body.appendChild(sandbox);
  try {
    const widthOf = (el: HTMLElement) => Math.ceil(el.getBoundingClientRect().width);
    const header = clones[0].map(widthOf);
    const natural = [...header];
    for (const rowClones of clones.slice(1)) {
      rowClones.forEach((clone, i) => {
        natural[i] = Math.max(natural[i], widthOf(clone));
      });
    }
    return { header, natural, visible };
  } finally {
    sandbox.remove();
  }
}

const useIsomorphicLayoutEffect =
  globalThis.window === undefined ? useEffect : useLayoutEffect;

type MeasuredNaturals = {
  key: string;
  header: number[];
  natural: number[];
  visible: boolean[];
};

/** One `<col>` per visible column; `id` is the column id or `trailingColumnId`. */
export type MeasuredColumnWidth = { id: string; width: number };

function sameNumbers(a: readonly number[], b: readonly number[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function visibilitySignature(visible: readonly boolean[]): string {
  return visible.map((v) => (v ? "1" : "0")).join("");
}

function sizingInputForColumn(
  col: AdminColumnInput,
  header: number,
  measured: number,
): ColumnSizingInput {
  const mode = resolveColumnSizingMode(col);
  if (mode === "fixed") {
    const px = resolveFixedColumnWidthPx(col) ?? measured;
    return { natural: px, header: px, mode };
  }
  const cap = cssLengthToPx(col.maxW);
  const uncapped = Math.max(header, measured);
  const minPx =
    cssLengthToPx(col.minWidth) ?? cssLengthToPx(compactColumnWidth(col));
  if (cap == null) {
    return { natural: uncapped, header, mode, minPx };
  }
  return {
    natural: Math.min(uncapped, cap),
    header: Math.min(header, cap),
    mode,
    minPx,
  };
}

/** Turn measured naturals into `<col>` pixel widths for the visible columns. */
export function buildMeasuredColumnWidths(options: Readonly<{
  naturals: MeasuredNaturals;
  key: string;
  available: number;
  columns: readonly AdminColumnInput[];
  trailingFixedPx?: number;
  trailingColumnId: string;
}>): MeasuredColumnWidth[] | null {
  const { naturals, key, available, columns, trailingFixedPx, trailingColumnId } =
    options;
  if (!naturals.key.startsWith(`${key}#`) || available <= 0) return null;

  const visibleIndexes = columns
    .map((_, i) => i)
    .filter((i) => naturals.visible[i]);
  const ids = visibleIndexes.map((i) => columns[i].id);
  const inputs: ColumnSizingInput[] = visibleIndexes.map((i) => {
    const header = naturals.header[i] ?? 0;
    return sizingInputForColumn(
      columns[i],
      header,
      naturals.natural[i] ?? header,
    );
  });
  if (trailingFixedPx) {
    inputs.push({ natural: trailingFixedPx, header: trailingFixedPx, mode: "fixed" });
    ids.push(trailingColumnId);
  }
  return distributeColumnWidths(inputs, available).map((width, i) => ({
    id: ids[i],
    width,
  }));
}

/** Measured `<colgroup>` widths for a fixed-layout table; null until first measure. */
export function useContentColumnWidths(options: Readonly<{
  tableRef: React.RefObject<HTMLTableElement>;
  containerRef: React.RefObject<HTMLElement>;
  columns: readonly AdminColumnInput[];
  trailingFixedPx?: number;
  trailingColumnId?: string;
  enabled: boolean;
  contentKey: unknown;
  /** Keep current widths (e.g. while searching); first measure still runs. */
  freeze?: boolean;
}>): MeasuredColumnWidth[] | null {
  const {
    tableRef,
    containerRef,
    columns,
    trailingFixedPx,
    trailingColumnId = "__trailing",
    enabled,
    contentKey,
    freeze = false,
  } = options;
  const [naturals, setNaturals] = useState<MeasuredNaturals | null>(null);
  const [available, setAvailable] = useState(0);
  const [fontsVersion, setFontsVersion] = useState(0);
  const key = `${fontsVersion}:${columns.map((c) => c.id).join("|")}`;

  useEffect(() => {
    let cancelled = false;
    document.fonts?.ready.then(() => {
      if (!cancelled) setFontsVersion((v) => v + 1);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useIsomorphicLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setAvailable(container.clientWidth);
    if (globalThis.ResizeObserver === undefined) return;
    const observer = new ResizeObserver(() => setAvailable(container.clientWidth));
    observer.observe(container);
    return () => observer.disconnect();
  }, [containerRef]);

  useIsomorphicLayoutEffect(() => {
    if (!enabled || !tableRef.current) return;
    const measured = measureColumnNaturalWidths(tableRef.current, columns.length);
    if (!measured) return;
    const measuredKey = `${key}#${visibilitySignature(measured.visible)}`;
    setNaturals((prev) => {
      if (prev?.key !== measuredKey) return { key: measuredKey, ...measured };
      if (freeze) return prev;
      const natural = measured.natural.map((n, i) => Math.max(n, prev.natural[i] ?? 0));
      const header = measured.header.map((n, i) => Math.max(n, prev.header[i] ?? 0));
      if (sameNumbers(natural, prev.natural) && sameNumbers(header, prev.header)) {
        return prev;
      }
      return { ...prev, header, natural };
    });
  }, [enabled, key, contentKey, columns.length, tableRef, available, freeze]);

  return useMemo(
    () =>
      naturals
        ? buildMeasuredColumnWidths({
            naturals,
            key,
            available,
            columns,
            trailingFixedPx,
            trailingColumnId,
          })
        : null,
    [naturals, key, available, columns, trailingFixedPx, trailingColumnId],
  );
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

/** Forces badges / stacks / text inside a fixed-layout cell to ellipsis. */
const TRUNCATING_CELL_SX = {
  "& > *": {
    maxWidth: "100%",
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  "& .chakra-badge": {
    display: "inline-block",
    maxWidth: "100%",
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    verticalAlign: "middle",
  },
  "& .chakra-stack, & .chakra-wrap": {
    maxWidth: "100%",
    minWidth: 0,
    overflow: "hidden",
  },
  "& .chakra-stack > *:first-of-type, & .chakra-wrap > *:first-of-type": {
    minWidth: 0,
    maxWidth: "100%",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
} as const;

/** Clip overflowing cell content; native `title` shows the full value on hover. */
export function TruncatingCellContent({
  children,
  ellipsis = true,
}: Readonly<{
  children: React.ReactNode;
  ellipsis?: boolean;
}>) {
  const ref = useRef<HTMLDivElement>(null);

  const onMouseEnter = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const text = (el.innerText ?? el.textContent ?? "")
      .replaceAll(/\s+/g, " ")
      .trim();
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
      w="100%"
      maxW="100%"
      overflow="hidden"
      textOverflow={ellipsis ? "ellipsis" : undefined}
      whiteSpace={ellipsis ? "nowrap" : undefined}
      sx={TRUNCATING_CELL_SX}
      onMouseEnter={onMouseEnter}
    >
      {children}
    </Box>
  );
}

/** Badge that truncates inside fixed-layout columns. */
export function TruncatingBadge({
  children,
  title,
  ...props
}: Readonly<BadgeProps & { title?: string }>) {
  const label =
    title ??
    (typeof children === "string" || typeof children === "number"
      ? String(children)
      : undefined);
  return (
    <Badge
      maxW="100%"
      minW={0}
      title={label}
      whiteSpace="nowrap"
      overflow="hidden"
      textOverflow="ellipsis"
      display="inline-block"
      verticalAlign="middle"
      {...props}
    >
      {children}
    </Badge>
  );
}
