import { CloseIcon } from "@chakra-ui/icons";
import {
  HStack,
  IconButton,
  Input,
  InputGroup,
  InputRightElement,
  Select,
  Th,
  Tooltip,
  Tr,
  VStack,
  type TableColumnHeaderProps,
} from "@chakra-ui/react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import type {
  DataTableColumnFilterConfig,
  DataTableColumnFilters,
} from "./dataTableTypes";

/** Packed form for `date_range` column filters (`from~to`, either side optional). */
export function encodeDateRangeFilter(from: string, to: string): string {
  const start = from.trim();
  const end = to.trim();
  if (!start && !end) return "";
  return `${start}~${end}`;
}

export function parseDateRangeFilter(value: string): { from: string; to: string } {
  const raw = value.trim();
  if (!raw) return { from: "", to: "" };
  const sep = raw.indexOf("~");
  if (sep < 0) return { from: raw, to: "" };
  return { from: raw.slice(0, sep).trim(), to: raw.slice(sep + 1).trim() };
}

/** Column fields the per-column search needs; keeps this file free of DataTable imports. */
export type FilterableColumn<T> = {
  id: string;
  header: React.ReactNode;
  /** `false` opts a column out of the automatic search box. */
  filter?: DataTableColumnFilterConfig | false;
  /** Value matched by client-side column search. Defaults to `sortAccessor`, then `row[id]`. Arrays match if any element equals the select value. */
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

/**
 * Every data column is sortable except Actions.
 * Toolbar filters may still own the same field for filtering; that must not
 * hide sort (Services Status / Task Type stay sortable with toolbar selects).
 */
export function withAutoColumnSort<T, C extends FilterableColumn<T> & { sortable?: boolean }>(
  columns: readonly C[],
): C[] {
  return columns.map((col) => {
    if (isActionsColumn(col)) {
      return { ...col, sortable: false };
    }
    return { ...col, sortable: true };
  });
}

function rowDateMillis<T>(col: FilterableColumn<T>, row: T): number | null {
  let raw: unknown;
  if (col.filterAccessor) {
    raw = col.filterAccessor(row);
  } else if (col.sortAccessor) {
    raw = col.sortAccessor(row);
  } else {
    raw = (row as Record<string, unknown>)[col.id];
  }
  if (typeof raw !== "number" || !Number.isFinite(raw) || raw <= 0) return null;
  if (raw === Number.POSITIVE_INFINITY) return null;
  return raw;
}

/** Inclusive local calendar-day bounds (`YYYY-MM-DD`), matching list API date_range. */
function rowMatchesDateRangeFilter<T>(
  col: FilterableColumn<T>,
  row: T,
  encoded: string,
): boolean {
  const { from, to } = parseDateRangeFilter(encoded);
  if (!from && !to) return true;
  const ms = rowDateMillis(col, row);
  if (ms == null) return false;
  if (from) {
    const start = Date.parse(`${from}T00:00:00`);
    if (!Number.isNaN(start) && ms < start) return false;
  }
  if (to) {
    const endDay = new Date(`${to}T00:00:00`);
    if (!Number.isNaN(endDay.getTime())) {
      endDay.setDate(endDay.getDate() + 1);
      if (ms >= endDay.getTime()) return false;
    }
  }
  return true;
}

function rowMatchesColumnFilter<T>(
  col: FilterableColumn<T>,
  row: T,
  index: number,
  needle: string,
): boolean {
  if (col.filter && col.filter.type === "date_range") {
    return rowMatchesDateRangeFilter(col, row, needle);
  }
  if (col.filter && col.filter.type === "select" && col.filterAccessor) {
    const raw = col.filterAccessor(row);
    if (Array.isArray(raw)) {
      return raw.some((value) => String(value).toLowerCase() === needle);
    }
    return valueText(raw).toLowerCase() === needle;
  }
  const texts = cellFilterTexts(col, row, index).map((text) => text.toLowerCase());
  if (col.filter && col.filter.type === "select") {
    return texts.includes(needle);
  }
  return texts.some((text) => text.includes(needle));
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
    active.every((col) =>
      rowMatchesColumnFilter(col, row, index, filters[col.id].toLowerCase()),
    ),
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
      <InputGroup size="sm" w="full" minW={0} maxW="100%">
        <Input
          {...FILTER_CONTROL_STYLE}
          pl={2}
          pr={draft ? 7 : 2}
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
          <InputRightElement h="100%" w={7}>
            <IconButton
              aria-label={`Clear ${name.toLowerCase()}`}
              icon={<CloseIcon boxSize="8px" />}
              size="xs"
              variant="ghost"
              minW={5}
              w={5}
              h={5}
              borderRadius="md"
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

/** Tall enough for 12px text + padding; focus stays inside the cell (no outer ring). */
const FILTER_CONTROL_STYLE = {
  h: "30px",
  minH: "30px",
  minW: 0,
  w: "100%",
  maxW: "100%",
  fontSize: "12px",
  lineHeight: "1.25",
  fontWeight: "normal",
  letterSpacing: "normal",
  textTransform: "none" as const,
  borderRadius: "6px",
  bg: "white",
  borderWidth: "1px",
  borderColor: "ink.200",
  color: "ink.800",
  boxShadow: "none",
  sx: {
    minWidth: "0 !important",
    boxSizing: "border-box",
  },
  _hover: { borderColor: "ink.300" },
  _focus: {
    borderColor: "blue.400",
    boxShadow: "none",
  },
  _focusVisible: {
    borderColor: "blue.500",
    boxShadow: "none",
  },
  _invalid: {
    borderColor: "red.400",
    boxShadow: "none",
  },
  _placeholder: { color: "ink.400", textOverflow: "ellipsis" },
} as const;

function DateRangeColumnFilterInput({
  label,
  config,
  value,
  onChange,
}: Readonly<{
  label: string;
  config: Extract<DataTableColumnFilterConfig, { type: "date_range" }>;
  value: string;
  onChange: (next: string) => void;
}>) {
  const parsed = parseDateRangeFilter(value);
  const [from, setFrom] = useState(parsed.from);
  const [to, setTo] = useState(parsed.to);
  const committed = useRef(value);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    committed.current = value;
    const next = parseDateRangeFilter(value);
    setFrom(next.from);
    setTo(next.to);
  }, [value]);

  const commit = useCallback((nextFrom: string, nextTo: string) => {
    const encoded = encodeDateRangeFilter(nextFrom, nextTo);
    if (encoded === committed.current.trim()) return;
    committed.current = encoded;
    onChangeRef.current(encoded);
  }, []);

  const clear = () => {
    setFrom("");
    setTo("");
    commit("", "");
  };

  return (
    <HStack spacing={1} align="center" minW={0} w="full">
      <VStack spacing={1} align="stretch" flex={1} minW={0}>
        <Input
          {...FILTER_CONTROL_STYLE}
          type="date"
          pl={2}
          pr={2}
          value={from}
          placeholder={config.fromPlaceholder ?? "From"}
          aria-label={`${label} from`}
          title={`${label} from`}
          onChange={(e) => {
            const next = e.target.value;
            setFrom(next);
            commit(next, to);
          }}
        />
        <Input
          {...FILTER_CONTROL_STYLE}
          type="date"
          pl={2}
          pr={2}
          value={to}
          placeholder={config.toPlaceholder ?? "To"}
          aria-label={`${label} to`}
          title={`${label} to`}
          onChange={(e) => {
            const next = e.target.value;
            setTo(next);
            commit(from, next);
          }}
        />
      </VStack>
      {from || to ? (
        <IconButton
          aria-label={`Clear ${label.toLowerCase()} dates`}
          icon={<CloseIcon boxSize="8px" />}
          size="xs"
          variant="ghost"
          minW={5}
          w={5}
          h={5}
          flexShrink={0}
          borderRadius="md"
          color="ink.500"
          onClick={clear}
        />
      ) : null}
    </HStack>
  );
}

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
        size="sm"
        {...FILTER_CONTROL_STYLE}
        pl={2}
        pr={8}
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
  if (config.type === "date_range") {
    return (
      <DateRangeColumnFilterInput
        label={label}
        config={config}
        value={value}
        onChange={onChange}
      />
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
          pt={1}
          pb={2.5}
          px={3}
          minW={0}
          maxW="100%"
          textTransform="none"
          letterSpacing="normal"
          fontWeight="normal"
          verticalAlign="middle"
          display={col.thProps?.display}
          sx={{
            // Keep the control inside the column; do not clip focus borders.
            overflow: "visible",
            "& > *": { minWidth: 0, maxWidth: "100%", display: "block" },
          }}
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
      {trailingCell ? <Th pt={1} pb={2.5} px={1} /> : null}
    </Tr>
  );
}
