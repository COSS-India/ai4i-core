import { Box, type TableCellProps } from "@chakra-ui/react";
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

/**
 * Badge / icon / code columns under `table-layout: fixed`.
 * Pin rem widths so they do not share leftover space equally with URL/name/error.
 * Keys are normalizeColumnId / compactColumnId forms.
 */
const COMPACT_COLUMN_WIDTHS: Record<string, string> = {
  // Fits "Unpublished" badge + hint/sort on Services; icon + STATUS on Logs.
  status: "8.5rem",
  level: "6.5rem",
  // Locale datetime / date — pin so they do not absorb leftover flex width.
  timestamp: "11.5rem",
  createdat: "11.5rem",
  created_at: "11.5rem",
  created: "7.5rem",
  // Short version tokens ("v6") — header still needs a little room for sort.
  version: "5.5rem",
  // "MODEL TASK TYPE" header + sort carets (Services).
  task: "10rem",
  modeltasktype: "10rem",
  // Shorter "TASK TYPE" header on Logs.
  tasktype: "7.75rem",
  task_type: "7.75rem",
  method: "5.25rem",
  statuscode: "6.75rem",
  status_code: "6.75rem",
  // Count columns (Models "No. of Services", Tier services/institutions).
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

function compactColumnWidth(col: { id: string }): string | undefined {
  const id = normalizeColumnId(col.id);
  return COMPACT_COLUMN_WIDTHS[id] ?? COMPACT_COLUMN_WIDTHS[compactColumnId(col.id)];
}

function isCompactColumn(col: { id: string }): boolean {
  return compactColumnWidth(col) != null;
}

/** Short, scannable values (dates, badges, counts) — sized to content, never truncated. */
const CONTENT_WIDTH_IDS = new Set([
  ...Object.keys(COMPACT_COLUMN_WIDTHS),
  "expires",
  "expiry",
  "expires_at",
  "budget",
  "allocation",
  "permissions",
  "latency",
  "updated",
  "updatedat",
  "updated_at",
  "published",
  "publishedat",
  "publishedon",
  "published_on",
  "inputprice",
  "outputprice",
  "cachedinputprice",
]);

function isContentWidthColumn(col: { id: string }): boolean {
  return (
    CONTENT_WIDTH_IDS.has(normalizeColumnId(col.id)) ||
    CONTENT_WIDTH_IDS.has(compactColumnId(col.id))
  );
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

/** Fixed rem rail for status / task-type / method-style columns. */
function pinnedCompactColumnLayout(col: AdminColumnInput): AdminColumnLayout {
  const width = compactColumnWidth(col) ?? "7.5rem";
  return {
    w: width,
    minW: width,
    maxW: width,
    whiteSpace: "nowrap",
  };
}

function primaryFlexPercent(otherCount: number): number {
  // Keep the lead column readable without eating half the table.
  return Math.min(22, Math.max(14, 38 - otherCount * 5));
}

function hasExplicitColumnWidth(col: AdminColumnInput): boolean {
  return col.width != null || col.minWidth != null || col.maxW != null;
}

/** `1%` / auto widths are shrink-wrap hints, not real pins under `table-layout: fixed`. */
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

/**
 * Actions / control columns must stay a pinned content-width rail.
 * Never absorb leftover table space; never crush to `1%` (truncates "Actions" → "A").
 */
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
    // Control columns win over generic explicit widths (incl. legacy `width: "1%"`).
    if (isShrinkWrapColumn(col)) {
      layouts.set(col.id, pinnedControlColumnLayout(col));
      continue;
    }
    if (hasExplicitColumnWidth(col)) {
      layouts.set(col.id, explicitColumnLayout(col));
      continue;
    }
    // Status / task type / method: pin rem width (do not flex with URL/name).
    if (isCompactColumn(col)) {
      layouts.set(col.id, pinnedCompactColumnLayout(col));
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

/**
 * - `fixed`: control rails and caller-pinned widths; never grow or shrink.
 * - `content`: dates, badges, counts; always show in full.
 * - `shrink`: free text; first to give up width, truncated with an ellipsis.
 */
export type ColumnSizingMode = "fixed" | "content" | "shrink";

export type ColumnSizingInput = {
  /** Widest of header and cells, px including cell padding. */
  natural: number;
  header: number;
  mode: ColumnSizingMode;
  minPx?: number;
};

/** Below this a truncated value stops being recognisable. */
const MIN_SHRINK_COLUMN_PX = 128;

export function resolveColumnSizingMode(col: AdminColumnInput): ColumnSizingMode {
  if (isShrinkWrapColumn(col)) return "fixed";
  if (col.width != null && !isFluidWidthHint(col.width)) return "fixed";
  if (isContentWidthColumn(col)) return "content";
  return "shrink";
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
  return Math.min(
    col.natural,
    Math.max(col.header, col.minPx ?? MIN_SHRINK_COLUMN_PX),
  );
}

/**
 * Content-first widths that fill `available`:
 * - room to spare: every non-fixed column grows in proportion to its content
 * - too tight: the widest `shrink` columns are levelled down first, never
 *   below their header or a readable minimum
 */
export function distributeColumnWidths(
  cols: readonly ColumnSizingInput[],
  available: number,
): number[] {
  const widths = cols.map((c) => c.natural);
  if (available <= 0) return widths;
  const total = widths.reduce((sum, w) => sum + w, 0);

  if (total <= available) {
    const growable = cols
      .map((c, i) => (c.mode === "fixed" ? -1 : i))
      .filter((i) => i >= 0);
    const weight = growable.reduce((sum, i) => sum + cols[i].natural, 0);
    if (weight > 0) {
      const extra = available - total;
      for (const i of growable) widths[i] += (extra * cols[i].natural) / weight;
    }
    return widths.map((w) => Math.floor(w));
  }

  const shrinkable = cols
    .map((c, i) => (c.mode === "shrink" ? i : -1))
    .filter((i) => i >= 0);
  const locked = cols.reduce(
    (sum, c) => (c.mode === "shrink" ? sum : sum + c.natural),
    0,
  );
  const budget = available - locked;
  const floors = cols.map(shrinkFloor);
  const widthAt = (level: number) =>
    shrinkable.reduce(
      (sum, i) => sum + Math.max(floors[i], Math.min(cols[i].natural, level)),
      0,
    );

  let level = 0;
  if (widthAt(0) < budget) {
    let lo = 0;
    let hi = Math.max(...shrinkable.map((i) => cols[i].natural));
    for (let step = 0; step < 24; step++) {
      const mid = (lo + hi) / 2;
      if (widthAt(mid) <= budget) lo = mid;
      else hi = mid;
    }
    level = lo;
  }
  for (const i of shrinkable) {
    widths[i] = Math.max(floors[i], Math.min(cols[i].natural, level));
  }
  return widths.map((w) => Math.round(w));
}

/**
 * Natural (unconstrained, single-line) width of each column, measured from
 * offscreen clones of the rendered header and body cells.
 *
 * `visible[i]` is false for columns hidden at the current breakpoint
 * (`display: none`); those drop out of the table's column structure, so
 * callers must not emit a `<col>` for them.
 */
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
  typeof globalThis.window === "undefined" ? useEffect : useLayoutEffect;

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

/**
 * Pixel widths for a fixed-layout table's `<colgroup>`, derived from the data
 * actually on screen. Returns null until the first measurement.
 *
 * Columns hidden at the current breakpoint are left out, so each width lands
 * on the column it was measured for. Widths only ratchet up while the visible
 * column set is unchanged, so paging or filtering does not make columns jump.
 */
export function useContentColumnWidths(options: Readonly<{
  tableRef: React.RefObject<HTMLTableElement>;
  containerRef: React.RefObject<HTMLElement>;
  columns: readonly AdminColumnInput[];
  trailingFixedPx?: number;
  trailingColumnId?: string;
  enabled: boolean;
  contentKey: unknown;
}>): MeasuredColumnWidth[] | null {
  const {
    tableRef,
    containerRef,
    columns,
    trailingFixedPx,
    trailingColumnId = "__trailing",
    enabled,
    contentKey,
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
    if (typeof globalThis.ResizeObserver === "undefined") return;
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
      const natural = measured.natural.map((n, i) => Math.max(n, prev.natural[i] ?? 0));
      const header = measured.header.map((n, i) => Math.max(n, prev.header[i] ?? 0));
      if (sameNumbers(natural, prev.natural) && sameNumbers(header, prev.header)) {
        return prev;
      }
      return { ...prev, header, natural };
    });
    // `available` re-measures when a resize crosses a breakpoint that hides columns.
  }, [enabled, key, contentKey, columns.length, tableRef, available]);

  return useMemo(() => {
    if (!naturals?.key.startsWith(`${key}#`) || available <= 0) return null;
    const visibleIndexes = columns
      .map((_, i) => i)
      .filter((i) => naturals.visible[i]);
    const ids = visibleIndexes.map((i) => columns[i].id);
    const inputs: ColumnSizingInput[] = visibleIndexes.map((i) => {
      const col = columns[i];
      const mode = resolveColumnSizingMode(col);
      const header = naturals.header[i] ?? 0;
      const measured = naturals.natural[i] ?? header;
      if (mode === "fixed") {
        const px = cssLengthToPx(col.width) ?? cssLengthToPx(col.maxW) ?? measured;
        return { natural: px, header: px, mode };
      }
      const cap = cssLengthToPx(col.maxW);
      return {
        natural: Math.max(header, cap == null ? measured : Math.min(measured, cap)),
        header,
        mode,
        minPx: cssLengthToPx(col.minWidth),
      };
    });
    if (trailingFixedPx) {
      inputs.push({ natural: trailingFixedPx, header: trailingFixedPx, mode: "fixed" });
      ids.push(trailingColumnId);
    }
    return distributeColumnWidths(inputs, available).map((width, i) => ({
      id: ids[i],
      width,
    }));
  }, [naturals, key, available, columns, trailingFixedPx, trailingColumnId]);
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
 * Clip overflowing cell content; native `title` tooltip with the full value
 * when anything inside is cut off. `ellipsis={false}` keeps the content's own
 * layout (badge rows, stacked lines) and only adds the hover title.
 */
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

  if (!ellipsis) {
    return (
      <Box ref={ref} minW={0} w="100%" maxW="100%" onMouseEnter={onMouseEnter}>
        {children}
      </Box>
    );
  }

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
