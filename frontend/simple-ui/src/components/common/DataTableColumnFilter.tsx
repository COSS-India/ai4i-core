import { CloseIcon } from "@chakra-ui/icons";
import {
  IconButton,
  Input,
  InputGroup,
  InputRightElement,
  Select,
  Th,
  Tooltip,
  Tr,
  type TableColumnHeaderProps,
} from "@chakra-ui/react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import type {
  DataTableColumnFilterConfig,
  DataTableColumnFilters,
} from "./dataTableTypes";

/** Column fields the per-column search needs; keeps this file free of DataTable imports. */
export type FilterableColumn<T> = {
  id: string;
  header: React.ReactNode;
  /** `false` opts a column out of the automatic search box. */
  filter?: DataTableColumnFilterConfig | false;
  /** Value matched by client-side column search. Defaults to `sortAccessor`, then `row[id]`. */
  filterAccessor?: (row: T) => unknown;
  sortAccessor?: (row: T) => string | number;
  cell?: (row: T, index: number) => React.ReactNode;
  thProps?: Pick<TableColumnHeaderProps, "display">;
};

const TEXT_FILTER_DEBOUNCE_MS = 400;

export function columnFilterLabel<T>(col: FilterableColumn<T>): string {
  return typeof col.header === "string" ? col.header : reactNodeText(col.header).trim();
}

/** Drops empty values so `{}` always means "no column search". */
export function setColumnFilterValue(
  filters: DataTableColumnFilters,
  columnId: string,
  value: string,
): DataTableColumnFilters {
  const next = { ...filters };
  const trimmed = value.trim();
  if (trimmed) next[columnId] = trimmed;
  else delete next[columnId];
  return next;
}

export function activeColumnFilterCount(filters: DataTableColumnFilters): number {
  return Object.values(filters).filter((v) => v.trim() !== "").length;
}

function valueText(value: unknown): string {
  if (value == null || typeof value === "boolean") return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(valueText).join(" ");
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "object") return Object.values(value).map(valueText).join(" ");
  return "";
}

/**
 * Visible text of a rendered cell. Custom components can't be rendered here,
 * so only their `children` are read; the raw row value covers the rest.
 */
export function reactNodeText(node: React.ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(reactNodeText).join(" ");
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    return reactNodeText(node.props.children);
  }
  return "";
}

/** Raw value and rendered text; a match on either counts. */
function cellFilterTexts<T>(col: FilterableColumn<T>, row: T, index: number): string[] {
  if (col.filterAccessor) return [valueText(col.filterAccessor(row))];
  const raw = col.sortAccessor
    ? col.sortAccessor(row)
    : (row as Record<string, unknown>)[col.id];
  const texts = [valueText(raw)];
  if (col.cell) texts.push(reactNodeText(col.cell(row, index)).trim());
  return texts;
}

function isActionsColumn<T>(col: FilterableColumn<T>): boolean {
  return col.id.toLowerCase() === "actions" || columnFilterLabel(col).toLowerCase() === "actions";
}

/**
 * Every column without a `filter` config gets a text search box, except
 * actions columns; `filter: false` opts out. `helper` explains the search scope.
 */
export function withAutoColumnFilters<T, C extends FilterableColumn<T>>(
  columns: readonly C[],
  helper?: string,
): C[] {
  return columns.map((col) =>
    col.filter === undefined && !isActionsColumn(col)
      ? { ...col, filter: { type: "text", helper } }
      : col,
  );
}

type ToolbarFilterRef = { id: string; param?: string; type?: string };

/** Normalize ids so `taskType` / `task_type` / `modelTaskType` all match `task`. */
function columnIdAliases(id: string): string[] {
  const raw = id.trim().toLowerCase();
  const compact = raw.replaceAll(/[_-]/g, "");
  const aliases = new Set<string>([raw, compact]);
  if (
    compact === "task" ||
    compact === "tasktype" ||
    compact === "modeltasktype" ||
    compact === "model_task_type".replaceAll("_", "")
  ) {
    aliases.add("task");
    aliases.add("tasktype");
    aliases.add("task_type");
    aliases.add("modeltasktype");
    aliases.add("model_task_type");
  }
  if (compact === "tenant" || compact === "institution" || compact === "tenantid") {
    aliases.add("tenant");
    aliases.add("institution");
    aliases.add("tenant_id");
  }
  if (compact === "level" || compact === "status") {
    aliases.add("status");
    aliases.add("level");
  }
  return Array.from(aliases);
}

/**
 * Toolbar select/date filters that already filter a column — that column
 * should not also expose header sort (same field in two places).
 */
export function toolbarBlockedSortColumnIds(
  filterDefs?: readonly ToolbarFilterRef[],
): Set<string> {
  const blocked = new Set<string>();
  for (const def of filterDefs ?? []) {
    if (def.type === "text") continue;
    for (const alias of columnIdAliases(def.id)) blocked.add(alias);
    if (def.param) {
      for (const alias of columnIdAliases(def.param)) blocked.add(alias);
    }
  }
  return blocked;
}

function isToolbarBlockedColumn(columnId: string, blocked: Set<string>): boolean {
  return columnIdAliases(columnId).some((alias) => blocked.has(alias));
}

/**
 * Shared sort rule for every admin table: every data column is sortable
 * except Actions and columns already owned by a toolbar filter.
 */
export function withAutoColumnSort<T, C extends FilterableColumn<T> & { sortable?: boolean }>(
  columns: readonly C[],
  filterDefs?: readonly ToolbarFilterRef[],
): C[] {
  const blocked = toolbarBlockedSortColumnIds(filterDefs);
  return columns.map((col) => {
    if (isActionsColumn(col) || isToolbarBlockedColumn(col.id, blocked)) {
      return { ...col, sortable: false };
    }
    return { ...col, sortable: true };
  });
}

/** Client-side match for tables that hold every row in memory. */
export function applyColumnFilters<T>(
  rows: readonly T[],
  columns: readonly FilterableColumn<T>[],
  filters: DataTableColumnFilters,
): T[] {
  const active = columns.filter((col) => col.filter && filters[col.id]);
  if (active.length === 0) return [...rows];
  return rows.filter((row, index) =>
    active.every((col) => {
      const needle = filters[col.id].toLowerCase();
      const texts = cellFilterTexts(col, row, index).map((text) => text.toLowerCase());
      return col.filter && col.filter.type === "select"
        ? texts.includes(needle)
        : texts.some((text) => text.includes(needle));
    }),
  );
}

/** Controlled when `value` is passed; otherwise DataTable keeps the state. */
export function useColumnFilterState(
  value: DataTableColumnFilters | undefined,
  onChange: ((next: DataTableColumnFilters) => void) | undefined,
): [DataTableColumnFilters, (next: DataTableColumnFilters) => void] {
  const [internal, setInternal] = useState<DataTableColumnFilters>({});
  const current = value ?? internal;
  const update = useCallback(
    (next: DataTableColumnFilters) => {
      if (value === undefined) setInternal(next);
      onChange?.(next);
    },
    [value, onChange],
  );
  return [current, update];
}

/** Applies after a pause in typing, or at once on Enter / blur; invalid input is never applied. */
function TextColumnFilterInput({
  label,
  config,
  value,
  onChange,
}: Readonly<{
  label: string;
  config: Extract<DataTableColumnFilterConfig, { type: "text" }>;
  value: string;
  onChange: (next: string) => void;
}>) {
  const [draft, setDraft] = useState(value);
  const committed = useRef(value);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const { validate } = config;

  useEffect(() => {
    committed.current = value;
    setDraft(value);
  }, [value]);

  const error = draft.trim() ? validate?.(draft.trim()) : undefined;

  const commit = useCallback(
    (next: string) => {
      if (next.trim() === committed.current.trim()) return;
      if (next.trim() && validate?.(next.trim())) return;
      committed.current = next;
      onChangeRef.current(next);
    },
    [validate],
  );

  useEffect(() => {
    const timer = setTimeout(() => commit(draft), TEXT_FILTER_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [draft, commit]);

  const clear = () => {
    setDraft("");
    commit("");
  };
  const name = `Search ${label}`.trim();

  return (
    <Tooltip label={error ?? config.helper} isDisabled={!error && !config.helper} hasArrow>
      <InputGroup size="xs">
        <Input
          {...FILTER_CONTROL_STYLE}
          pr={draft ? 6 : 2}
          value={draft}
          placeholder={config.placeholder ?? "Search"}
          aria-label={name}
          title={error || config.helper ? undefined : name}
          isInvalid={Boolean(error)}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => commit(draft)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit(draft);
            if (e.key === "Escape" && draft) clear();
          }}
        />
        {draft ? (
          <InputRightElement h="28px" w={6}>
            <IconButton
              aria-label={`Clear ${name.toLowerCase()}`}
              icon={<CloseIcon boxSize="7px" />}
              size="xs"
              variant="ghost"
              minW={5}
              h={5}
              color="ink.500"
              onMouseDown={(e) => e.preventDefault()}
              onClick={clear}
            />
          </InputRightElement>
        ) : null}
      </InputGroup>
    </Tooltip>
  );
}

const FILTER_CONTROL_STYLE = {
  h: "28px",
  minW: 0,
  w: "100%",
  fontSize: "12px",
  fontWeight: "normal",
  borderRadius: "6px",
  bg: "white",
  borderColor: "ink.200",
  color: "ink.800",
  _hover: { borderColor: "ink.300" },
  _placeholder: { color: "ink.400" },
} as const;

function ColumnFilterInput({
  label,
  config,
  value,
  onChange,
}: Readonly<{
  label: string;
  config: DataTableColumnFilterConfig;
  value: string;
  onChange: (next: string) => void;
}>) {
  if (config.type === "select") {
    return (
      <Select
        size="xs"
        {...FILTER_CONTROL_STYLE}
        value={value}
        aria-label={`Filter ${label}`}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">All</option>
        {config.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
    );
  }
  return (
    <TextColumnFilterInput label={label} config={config} value={value} onChange={onChange} />
  );
}

/**
 * Second header row with a search box under each searchable column.
 * Renders nothing when no column opts in.
 */
export function ColumnFilterRow<T>({
  columns,
  filters,
  onChange,
  trailingCell,
}: Readonly<{
  columns: readonly FilterableColumn<T>[];
  filters: DataTableColumnFilters;
  onChange: (next: DataTableColumnFilters) => void;
  /** Keeps the row aligned when the table has an extra trailing column. */
  trailingCell?: boolean;
}>) {
  if (!columns.some((col) => col.filter)) return null;
  return (
    <Tr>
      {columns.map((col) => (
        <Th
          key={col.id}
          pt={0}
          pb={2}
          px={2}
          textTransform="none"
          letterSpacing="normal"
          overflow="hidden"
          display={col.thProps?.display}
        >
          {col.filter ? (
            <ColumnFilterInput
              label={columnFilterLabel(col)}
              config={col.filter}
              value={filters[col.id] ?? ""}
              onChange={(value) => onChange(setColumnFilterValue(filters, col.id, value))}
            />
          ) : null}
        </Th>
      ))}
      {trailingCell ? <Th pt={0} pb={2} /> : null}
    </Tr>
  );
}
