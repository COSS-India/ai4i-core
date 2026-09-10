import { ChevronRightIcon, SearchIcon } from "@chakra-ui/icons";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Center,
  FormControl,
  FormControlProps,
  Input,
  InputGroup,
  InputGroupProps,
  InputLeftElement,
  InputProps,
  Select,
  SelectProps,
  Spinner,
  Table,
  TableCellProps,
  TableContainer,
  TableContainerProps,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
  type TableProps,
} from "@chakra-ui/react";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  DEFAULT_PAGE_SIZE_OPTIONS,
  useAdminDataTable,
  useAdminDataTableServer,
  type UseAdminDataTableServerOptions,
} from "../../hooks/useAdminDataTable";
import { useTableSort, type TableSortDirection } from "../../utils/tableSort";
import FieldHint from "./FieldHint";
import FieldLabel from "./FieldLabel";
import {
  TableFilterToolbar,
  TablePaginationBar,
  TableSortHeader,
  useAdminTableSurface,
} from "./TableControls";
import type {
  DataTableFilterDef,
  DataTableSearchConfig,
  DataTableSortState,
} from "./dataTableTypes";
import {
  DATA_TABLE_CELL_MAX_W,
  TruncatingCellContent,
  getTruncateCellProps,
  shouldAutoTruncateColumn,
} from "./dataTableUtils";

export { DATA_TABLE_CELL_MAX_W };
export type { DataTableSortDirection } from "./dataTableTypes";
export type {
  DataTableFilterDef,
  DataTableFilterOption,
  DataTableSearchConfig,
  DataTableSortState,
} from "./dataTableTypes";

/** Default uppercase header styling shared across app tables. */
export const DATA_TABLE_HEADER_SX = {
  fontSize: "11.5px",
  letterSpacing: "0.05em",
  color: "gray.500",
  textTransform: "uppercase" as const,
} as const;

export type DataTableLayout = "card" | "admin";

/** One column in a {@link DataTable}. */
export interface DataTableColumn<T> {
  id: string;
  header: React.ReactNode;
  /**
   * Optional circled-i tooltip on the header.
   * Alias of `hint` for older call sites.
   */
  tip?: string;
  /** Optional circled-i tooltip on the header (preferred name). */
  hint?: string;
  /**
   * When true, DataTable renders sort UI.
   * - Card: click-to-toggle header (client sort unless `onSortChange` is set)
   * - Admin: asc/desc buttons driven by `sort` / `onSortChange`
   */
  sortable?: boolean;
  /**
   * Backend / emitted sort field when different from `id`.
   * Used by `onSortChange` payloads; defaults to `id`.
   */
  sortKey?: string;
  /** Value used for client-side sorting (card layout, or admin when parent does not own sort). */
  sortAccessor?: (row: T) => string | number;
  /**
   * Admin layout: ellipsis-truncate cell content when true.
   * Auto-skipped for action/control columns unless explicitly true.
   */
  truncate?: boolean;
  maxW?: TableCellProps["maxW"];
  thProps?: TableCellProps;
  tdProps?: TableCellProps;
  width?: string;
  minWidth?: string;
  isNumeric?: boolean;
  /** Text alignment for header/cells. */
  align?: "left" | "center" | "right";
  cell: (row: T, index: number) => React.ReactNode;
  /** Card layout: optional footer cell (enable with `showFooter`). */
  footer?: React.ReactNode;
}

function columnHint<T>(col: DataTableColumn<T>): string | undefined {
  return col.hint ?? col.tip;
}

function columnSortKey<T>(col: DataTableColumn<T>): string {
  return col.sortKey ?? col.id;
}

interface DataTableSharedProps<T> {
  columns: DataTableColumn<T>[];
  isLoading?: boolean;
  onRowClick?: (row: T) => void;
}

/** Card layout props — dashboards, drill-down lists, drawers. */
export interface DataTableCardProps<T> extends DataTableSharedProps<T> {
  layout?: "card";
  rows: readonly T[];
  rowKey: (row: T) => string | number;
  defaultSortKey?: string;
  defaultSortDirection?: TableSortDirection;
  /** When false, sorting UI is hidden and row order is preserved. Default true. */
  sortable?: boolean;
  /**
   * Parent-owned sort. When set with `onSortChange`, DataTable emits sort events
   * and does not reorder rows (parent / API owns order).
   */
  sort?: DataTableSortState;
  onSortChange?: (next: DataTableSortState) => void;
  showAsyncState?: boolean;
  isEmpty?: boolean;
  errorMessage?: string | null;
  emptyMessage?: string;
  asyncStateHeight?: string | number;
  rowAriaLabel?: (row: T) => string;
  showRowChevron?: boolean;
  renderAfterRow?: (row: T) => React.ReactNode | null;
  showFooter?: boolean;
  variant?: "default" | "compact";
  borderRadius?: string;
  theadBg?: string;
  cellPy?: number | string;
  tableMinWidth?: string;
  containerMt?: number | string;
  tableProps?: Omit<TableProps, "size" | "variant">;
}

/** Admin layout props — profile/admin pages with filters and pagination. */
export interface DataTableAdminProps<T> extends DataTableSharedProps<T> {
  layout: "admin";
  items: T[];
  getRowKey: (row: T) => string;
  /**
   * Config-driven search input owned by DataTable.
   * Parent performs filtering / API requests via `search.onChange`.
   */
  search?: DataTableSearchConfig;
  /**
   * Config-driven filter controls (`select`, `text`, `date`; `multiselect` reserved).
   * Parent maps values → API via each filter’s `onChange` / `param`.
   * `param` / `search.fields` are documentation for call sites — DataTable does not read them.
   */
  filterDefs?: DataTableFilterDef[];
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
  filterToolbarAlign?: "flex-start" | "center";
  filterToolbarRightContent?: React.ReactNode;
  showFiltersHeading?: boolean;
  filtersHeading?: string;
  /**
   * Parent-owned sort state. Pair with column `sortable: true` and `onSortChange`.
   */
  sort?: DataTableSortState;
  onSortChange?: (next: DataTableSortState) => void;
  paginate?: "client" | "server" | false;
  initialPageSize?: number;
  pageSizeOptions?: readonly number[];
  serverPagination?: UseAdminDataTableServerOptions;
  loadingMessage?: string;
  emptyMessage?: string;
  noResultsMessage?: string;
  unfilteredCount?: number;
  maxHeight?: string;
  tableContainerProps?: Omit<TableContainerProps, "children">;
  size?: "sm" | "md";
  paginationPosition?: "top" | "bottom";
  /** Match card-layout drill-down affordance when rows are clickable. Default: true when `onRowClick` is set. */
  showRowChevron?: boolean;
}

export type DataTableProps<T> = DataTableCardProps<T> | DataTableAdminProps<T>;

function buildSortAccessors<T>(columns: DataTableColumn<T>[]): Record<string, (row: T) => string | number> {
  const accessors: Record<string, (row: T) => string | number> = {};
  for (const col of columns) {
    if (!col.sortable) continue;
    accessors[col.id] =
      col.sortAccessor ??
      ((row: T) => {
        const value = (row as Record<string, unknown>)[col.id];
        if (typeof value === "number" || typeof value === "string") return value;
        return String(value ?? "");
      });
  }
  return accessors;
}

type DataTableFilterContextValue = {
  resetPage: () => void;
  inputBg: string;
};

const DataTableFilterContext = createContext<DataTableFilterContextValue>({
  resetPage: () => {},
  inputBg: "white",
});

function useDataTableFilterContext() {
  return useContext(DataTableFilterContext);
}

/** Search field wired to reset pagination when the value changes. */
export function TableSearchField({
  label = "Search",
  value,
  onChange,
  placeholder,
  helper,
  hint,
  debounceMs,
  formControlProps,
  inputGroupProps,
  inputProps,
}: {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  helper?: string;
  hint?: string;
  debounceMs?: number;
  formControlProps?: FormControlProps;
  inputGroupProps?: Omit<InputGroupProps, "children">;
  inputProps?: Omit<InputProps, "value" | "onChange" | "placeholder">;
}) {
  const { resetPage, inputBg } = useDataTableFilterContext();
  const [localValue, setLocalValue] = useState(value);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const emitChange = useCallback(
    (next: string) => {
      onChange(next);
      resetPage();
    },
    [onChange, resetPage],
  );

  const handleChange = (next: string) => {
    setLocalValue(next);
    if (!debounceMs || debounceMs <= 0) {
      emitChange(next);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => emitChange(next), debounceMs);
  };

  return (
    <FormControl w={{ base: "full", md: "320px" }} {...formControlProps}>
      <FieldLabel hint={hint}>{label}</FieldLabel>
      <InputGroup size="sm" {...inputGroupProps}>
        <InputLeftElement pointerEvents="none">
          <SearchIcon color="gray.400" />
        </InputLeftElement>
        <Input
          value={localValue}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
          bg={inputBg}
          pl={9}
          aria-label={label}
          {...inputProps}
        />
      </InputGroup>
      <FieldHint>{helper}</FieldHint>
    </FormControl>
  );
}

/** Plain text/number field wired to reset pagination when the value changes. */
export function TableTextField({
  label,
  value,
  onChange,
  placeholder,
  helper,
  hint,
  inputType = "text",
  formControlProps,
  inputProps,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  helper?: string;
  hint?: string;
  inputType?: "text" | "number";
  formControlProps?: FormControlProps;
  inputProps?: Omit<InputProps, "value" | "onChange" | "placeholder" | "type">;
}) {
  const { resetPage, inputBg } = useDataTableFilterContext();

  return (
    <FormControl w={{ base: "full", sm: "200px" }} {...formControlProps}>
      <FieldLabel hint={hint}>{label}</FieldLabel>
      <Input
        type={inputType}
        size="sm"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          resetPage();
        }}
        placeholder={placeholder}
        bg={inputBg}
        aria-label={label}
        {...inputProps}
      />
      <FieldHint>{helper}</FieldHint>
    </FormControl>
  );
}

/** Date / datetime-local field wired to reset pagination when the value changes. */
export function TableDateField({
  label,
  value,
  onChange,
  helper,
  hint,
  inputType = "date",
  formControlProps,
  inputProps,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  helper?: string;
  hint?: string;
  inputType?: "date" | "datetime-local";
  formControlProps?: FormControlProps;
  inputProps?: Omit<InputProps, "value" | "onChange" | "type">;
}) {
  const { resetPage, inputBg } = useDataTableFilterContext();

  return (
    <FormControl w={{ base: "full", sm: "220px" }} {...formControlProps}>
      <FieldLabel hint={hint}>{label}</FieldLabel>
      <Input
        type={inputType}
        size="sm"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          resetPage();
        }}
        bg={inputBg}
        aria-label={label}
        {...inputProps}
      />
      <FieldHint>{helper}</FieldHint>
    </FormControl>
  );
}

/** Select field wired to reset pagination when the value changes. */
export function TableSelectField({
  label,
  value,
  onChange,
  children,
  helper,
  hint,
  formControlProps,
  selectProps,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  helper?: string;
  hint?: string;
  formControlProps?: FormControlProps;
  selectProps?: Omit<SelectProps, "value" | "onChange" | "children">;
}) {
  const { resetPage, inputBg } = useDataTableFilterContext();
  return (
    <FormControl w={{ base: "full", sm: "200px" }} {...formControlProps}>
      <FieldLabel hint={hint}>{label}</FieldLabel>
      <Select
        size="sm"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          resetPage();
        }}
        bg={inputBg}
        aria-label={label}
        {...selectProps}
      >
        {children}
      </Select>
      <FieldHint>{helper}</FieldHint>
    </FormControl>
  );
}

function ConfigDrivenFilters({
  search,
  filterDefs,
}: {
  search?: DataTableSearchConfig;
  filterDefs?: DataTableFilterDef[];
}) {
  return (
    <>
      {search ? (
        <TableSearchField
          label={search.label ?? "Search"}
          value={search.value}
          onChange={search.onChange}
          placeholder={search.placeholder}
          helper={search.helper}
          debounceMs={search.debounceMs}
        />
      ) : null}
      {(filterDefs ?? []).map((def) => {
        const widthProps = def.width
          ? { w: def.width as FormControlProps["w"] }
          : undefined;

        if (def.type === "select") {
          return (
            <TableSelectField
              key={def.id}
              label={def.label}
              value={def.value}
              onChange={def.onChange}
              helper={def.helper}
              formControlProps={widthProps ? { w: widthProps.w } : undefined}
            >
              {(def.options ?? []).map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </TableSelectField>
          );
        }

        if (def.type === "text") {
          const textType = def.inputType === "number" ? "number" : "text";
          return (
            <TableTextField
              key={def.id}
              label={def.label}
              value={def.value}
              onChange={def.onChange}
              placeholder={def.placeholder}
              helper={def.helper}
              inputType={textType}
              formControlProps={widthProps ? { w: widthProps.w } : undefined}
              inputProps={textType === "number" ? { min: 0 } : undefined}
            />
          );
        }

        if (def.type === "date") {
          const dateType =
            def.inputType === "datetime-local" ? "datetime-local" : "date";
          return (
            <TableDateField
              key={def.id}
              label={def.label}
              value={def.value}
              onChange={def.onChange}
              helper={def.helper}
              inputType={dateType}
              formControlProps={widthProps ? { w: widthProps.w } : undefined}
            />
          );
        }

        // Reserved: multiselect is not implemented yet — fail loudly in dev
        // so a misconfigured filterDefs entry is obvious (renders nothing otherwise).
        if (process.env.NODE_ENV !== "production") {
          // eslint-disable-next-line no-console
          console.warn(
            `[DataTable] filterDefs type "${def.type}" is not rendered yet (id="${def.id}").`,
          );
        }
        return null;
      })}
    </>
  );
}

function AdminSortableHeader<T>({
  col,
  sort,
  onSortChange,
}: {
  col: DataTableColumn<T>;
  sort?: DataTableSortState;
  onSortChange?: (next: DataTableSortState) => void;
}) {
  const hint = columnHint(col);

  if (col.sortable && onSortChange) {
    const key = columnSortKey(col);
    const labelText = typeof col.header === "string" ? col.header : String(col.header ?? key);
    const isActive = Boolean(sort && (sort.key === key || sort.key === col.id));
    const direction = isActive && sort ? sort.direction : "asc";
    return (
      <TableSortHeader
        label={labelText}
        direction={direction}
        active={isActive}
        hint={hint}
        onAsc={() => onSortChange({ key, direction: "asc" })}
        onDesc={() => onSortChange({ key, direction: "desc" })}
        ascAriaLabel={`Sort ${labelText} ascending`}
        descAriaLabel={`Sort ${labelText} descending`}
      />
    );
  }

  if (typeof col.header === "string" || hint) {
    return (
      <FieldLabel variant="header" hint={hint}>
        {col.header}
      </FieldLabel>
    );
  }

  return <>{col.header}</>;
}

function CardLayoutDataTable<T>({
  columns,
  rows,
  rowKey,
  defaultSortKey,
  defaultSortDirection = "asc",
  sortable: sortingEnabled = true,
  sort: controlledSort,
  onSortChange,
  showAsyncState = true,
  isLoading = false,
  isEmpty = false,
  errorMessage = null,
  emptyMessage = "No data available.",
  asyncStateHeight = "200px",
  onRowClick,
  rowAriaLabel,
  showRowChevron = false,
  renderAfterRow,
  showFooter = false,
  variant = "default",
  borderRadius = variant === "compact" ? "10px" : "14px",
  theadBg = "#FAFBFD",
  cellPy = variant === "compact" ? 3 : 4,
  tableMinWidth,
  containerMt = variant === "compact" ? 0 : 1,
  tableProps,
}: DataTableCardProps<T>) {
  const sortAccessors = useMemo(() => buildSortAccessors(columns), [columns]);
  const initialSortKey = defaultSortKey ?? columns.find((c) => c.sortable)?.id ?? columns[0]?.id ?? "";
  const parentOwnsSort = Boolean(onSortChange);

  const { sortedRows, sortKey, sortDirection, setSortState } = useTableSort(
    rows,
    initialSortKey,
    sortAccessors,
    defaultSortDirection,
  );

  const activeSortKey = parentOwnsSort ? (controlledSort?.key ?? "") : sortKey;
  const activeSortDirection = parentOwnsSort
    ? (controlledSort?.direction ?? defaultSortDirection)
    : sortDirection;

  const handleSortChange = (next: DataTableSortState) => {
    if (parentOwnsSort && onSortChange) {
      onSortChange(next);
      return;
    }
    setSortState(next);
  };

  const displayRows = sortingEnabled && !parentOwnsSort ? sortedRows : [...rows];
  const hasFooter = showFooter && columns.some((c) => c.footer != null);
  const clickable = Boolean(onRowClick);

  const table = (
    <Box
      overflowX="auto"
      mt={containerMt}
      borderWidth="1px"
      borderColor="gray.300"
      borderRadius={borderRadius}
      bg="white"
    >
      <Table
        size="sm"
        variant="simple"
        minW={tableMinWidth}
        sx={{ "th, td": { verticalAlign: "middle" } }}
        {...tableProps}
      >
        <Thead bg={theadBg}>
          <Tr>
            {columns.map((col) => {
              const hint = columnHint(col);
              const headerSx = {
                ...DATA_TABLE_HEADER_SX,
                ...(col.isNumeric || col.align === "right" ? { textAlign: "right" as const } : {}),
                ...(col.align === "center" ? { textAlign: "center" as const } : {}),
              };
              return (
                <Th
                  key={col.id}
                  w={col.width}
                  minW={col.minWidth}
                  isNumeric={col.isNumeric}
                  sx={headerSx}
                >
                  {sortingEnabled && col.sortable ? (
                    <AdminSortableHeader
                      col={col}
                      sort={{ key: activeSortKey, direction: activeSortDirection }}
                      onSortChange={handleSortChange}
                    />
                  ) : hint ? (
                    <FieldLabel variant="header" hint={hint}>
                      {col.header}
                    </FieldLabel>
                  ) : (
                    col.header
                  )}
                </Th>
              );
            })}
            {showRowChevron ? <Th w="4%" borderBottomWidth="1px" sx={DATA_TABLE_HEADER_SX} /> : null}
          </Tr>
        </Thead>
        <Tbody>
          {displayRows.map((row, index) => {
            const key = rowKey(row);
            const rowProps = clickable
              ? {
                  role: "button" as const,
                  tabIndex: 0,
                  "aria-label": rowAriaLabel?.(row),
                  cursor: "pointer" as const,
                  _hover: {
                    bg: "#FAFBFE",
                    "& .data-table-chevron": { color: "blue.500" },
                  },
                  onClick: () => onRowClick?.(row),
                  onKeyDown: (e: React.KeyboardEvent) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onRowClick?.(row);
                    }
                  },
                }
              : {};

            return (
              <React.Fragment key={key}>
                <Tr {...rowProps}>
                  {columns.map((col) => (
                    <Td
                      key={col.id}
                      py={cellPy}
                      isNumeric={col.isNumeric}
                      textAlign={col.align}
                    >
                      {col.cell(row, index)}
                    </Td>
                  ))}
                  {showRowChevron ? (
                    <Td py={cellPy} textAlign="right">
                      <ChevronRightIcon className="data-table-chevron" boxSize={3.5} color="gray.300" />
                    </Td>
                  ) : null}
                </Tr>
                {renderAfterRow?.(row) ?? null}
              </React.Fragment>
            );
          })}
          {hasFooter ? (
            <Tr bg={theadBg}>
              {columns.map((col) => (
                <Td key={col.id} py={cellPy} fontWeight="extrabold" fontSize="13px" color="gray.800">
                  {col.footer ?? null}
                </Td>
              ))}
              {showRowChevron ? <Td py={cellPy} /> : null}
            </Tr>
          ) : null}
        </Tbody>
      </Table>
    </Box>
  );

  if (!showAsyncState) return table;

  if (isLoading) {
    return (
      <Center h={asyncStateHeight}>
        <Spinner size="lg" color="orange.500" />
      </Center>
    );
  }

  if (errorMessage) {
    return (
      <Alert status="error" borderRadius="md" fontSize="sm">
        <AlertIcon />
        <AlertDescription>{errorMessage}</AlertDescription>
      </Alert>
    );
  }

  if (isEmpty) {
    return (
      <Center h={asyncStateHeight}>
        <Text color="gray.500">{emptyMessage}</Text>
      </Center>
    );
  }

  return table;
}

function AdminLayoutDataTable<T>({
  items,
  columns,
  getRowKey,
  search,
  filterDefs,
  hasActiveFilters = false,
  onClearFilters,
  filterToolbarAlign = "flex-start",
  filterToolbarRightContent,
  showFiltersHeading = false,
  filtersHeading = "Filters",
  sort,
  onSortChange,
  paginate = "client",
  initialPageSize = 25,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  serverPagination,
  isLoading = false,
  loadingMessage = "Loading…",
  emptyMessage = "No items found.",
  noResultsMessage = "No items match the current filters.",
  unfilteredCount,
  onRowClick,
  maxHeight = "60vh",
  tableContainerProps,
  size = "sm",
  paginationPosition = "bottom",
  showRowChevron,
}: DataTableAdminProps<T>) {
  const { cardBg } = useAdminTableSurface();
  const rowChevron = showRowChevron ?? Boolean(onRowClick);

  const clientTable = useAdminDataTable(paginate === "client" ? items : [], {
    initialPageSize,
    pageSizeOptions,
  });

  const serverTable = useAdminDataTableServer(
    serverPagination ?? {
      page: 1,
      pageSize: initialPageSize,
      totalItems: 0,
      onPageChange: () => {},
      onPageSizeChange: () => {},
      pageSizeOptions,
    },
  );

  const displayItems = paginate === "client" ? clientTable.paginatedItems : items;

  const pagination =
    paginate === "client"
      ? {
          startRow: clientTable.startRow,
          endRow: clientTable.endRow,
          totalItems: clientTable.totalItems,
          page: clientTable.page,
          totalPages: clientTable.totalPages,
          pageSize: clientTable.pageSize,
          pageSizeOptions: clientTable.pageSizeOptions,
          onPageSizeChange: clientTable.setPageSizeAndReset,
          onFirst: () => clientTable.setPage(1),
          onPrev: () => clientTable.setPage((p) => Math.max(1, p - 1)),
          onNext: () => clientTable.setPage((p) => Math.min(clientTable.totalPages, p + 1)),
          onLast: () => clientTable.setPage(clientTable.totalPages),
          canPrev: clientTable.canPrev,
          canNext: clientTable.canNext,
          resetPage: clientTable.resetPage,
        }
      : paginate === "server" && serverPagination
        ? {
            startRow: serverTable.startRow,
            endRow: serverTable.endRow,
            totalItems: serverTable.totalItems,
            page: serverTable.page,
            totalPages: serverTable.totalPages,
            pageSize: serverTable.pageSize,
            pageSizeOptions: serverTable.pageSizeOptions,
            onPageSizeChange: serverTable.setPageSizeAndReset,
            onFirst: serverTable.goFirst,
            onPrev: serverTable.goPrev,
            onNext: serverTable.goNext,
            onLast: serverTable.goLast,
            canPrev: serverTable.canPrev,
            canNext: serverTable.canNext,
            resetPage: () => serverPagination?.onPageChange(1),
          }
        : null;

  const handleClearFilters = useCallback(() => {
    onClearFilters?.();
    pagination?.resetPage();
  }, [onClearFilters, pagination?.resetPage]);

  const filterContextValue = useMemo(
    () => ({
      resetPage: pagination?.resetPage ?? (() => {}),
      inputBg: cardBg,
    }),
    [pagination?.resetPage, cardBg],
  );

  const showEmpty =
    !isLoading &&
    (paginate === "server"
      ? (serverPagination?.totalItems ?? 0) === 0
      : paginate === "client"
        ? clientTable.totalItems === 0
        : items.length === 0);

  const emptyText =
    hasActiveFilters || (unfilteredCount != null && unfilteredCount > 0)
      ? noResultsMessage
      : emptyMessage;

  const paginationBlock =
    paginate !== false && pagination && pagination.totalItems > 0 ? (
      <TablePaginationBar
        startRow={pagination.startRow}
        endRow={pagination.endRow}
        totalItems={pagination.totalItems}
        page={pagination.page}
        totalPages={pagination.totalPages}
        pageSize={pagination.pageSize}
        pageSizeOptions={pagination.pageSizeOptions}
        onPageSizeChange={pagination.onPageSizeChange}
        onFirst={pagination.onFirst}
        onPrev={pagination.onPrev}
        onNext={pagination.onNext}
        onLast={pagination.onLast}
        canPrev={pagination.canPrev}
        canNext={pagination.canNext}
        borderColor="gray.300"
        bg="#FAFBFD"
        variant="attached"
        placement={paginationPosition}
      />
    ) : null;

  const hasFilterToolbar = Boolean(search || (filterDefs && filterDefs.length > 0));

  // Outer shell owns border/radius; strip chrome overrides from container props.
  const {
    borderWidth: _borderWidth,
    borderColor: _borderColor,
    borderRadius: _borderRadius,
    bg: _bg,
    overflow: _overflow,
    maxH: containerMaxH,
    ...restTableContainerProps
  } = tableContainerProps ?? {};

  const tableBody = (
    <TableContainer
      maxH={containerMaxH ?? maxHeight}
      overflowY="auto"
      overflowX="auto"
      bg="white"
      {...restTableContainerProps}
    >
      <Table
        variant="simple"
        bg="white"
        size={size}
        w="100%"
        sx={{ "th, td": { verticalAlign: "middle" } }}
      >
        <Thead bg="#FAFBFD" position="sticky" top={0} zIndex={1}>
          <Tr>
            {columns.map((col) => {
              const truncate = shouldAutoTruncateColumn(col);
              const headerSx = {
                ...DATA_TABLE_HEADER_SX,
                ...(col.isNumeric || col.align === "right"
                  ? { textAlign: "right" as const }
                  : {}),
                ...(col.align === "center" ? { textAlign: "center" as const } : {}),
              };
              return (
                <Th
                  key={col.id}
                  py={3}
                  w={col.width}
                  minW={col.minWidth}
                  sx={headerSx}
                  {...getTruncateCellProps(truncate, col.maxW)}
                  {...col.thProps}
                >
                  <AdminSortableHeader col={col} sort={sort} onSortChange={onSortChange} />
                </Th>
              );
            })}
            {rowChevron ? <Th w="4%" py={3} sx={DATA_TABLE_HEADER_SX} /> : null}
          </Tr>
        </Thead>
        <Tbody>
          {displayItems.map((row, index) => (
            <Tr
              key={getRowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              cursor={onRowClick ? "pointer" : undefined}
              _hover={{
                bg: "#FAFBFE",
                ...(rowChevron ? { "& .data-table-chevron": { color: "blue.500" } } : {}),
              }}
              transition="background 0.15s"
            >
              {columns.map((col) => {
                const truncate = shouldAutoTruncateColumn(col);
                const content = col.cell(row, index);
                return (
                  <Td
                    key={col.id}
                    py={4}
                    isNumeric={col.isNumeric}
                    textAlign={col.align}
                    {...getTruncateCellProps(truncate, col.maxW)}
                    {...col.tdProps}
                  >
                    {truncate ? (
                      <TruncatingCellContent>{content}</TruncatingCellContent>
                    ) : (
                      content
                    )}
                  </Td>
                );
              })}
              {rowChevron ? (
                <Td py={4} textAlign="right">
                  <ChevronRightIcon
                    className="data-table-chevron"
                    boxSize={3.5}
                    color="gray.300"
                  />
                </Td>
              ) : null}
            </Tr>
          ))}
        </Tbody>
      </Table>
    </TableContainer>
  );

  return (
    <DataTableFilterContext.Provider value={filterContextValue}>
      <VStack spacing={4} align="stretch" w="100%">
        {hasFilterToolbar ? (
          <VStack spacing={4} align="stretch">
            {showFiltersHeading ? (
              <Text fontSize="sm" fontWeight="semibold" color="gray.700" userSelect="none">
                {filtersHeading}
              </Text>
            ) : null}
            <TableFilterToolbar
              hasActiveFilters={hasActiveFilters}
              onClear={onClearFilters ? handleClearFilters : undefined}
              align={filterToolbarAlign}
              rightContent={filterToolbarRightContent}
            >
              <ConfigDrivenFilters search={search} filterDefs={filterDefs} />
            </TableFilterToolbar>
          </VStack>
        ) : null}

        {isLoading ? (
          <Center py={8}>
            <VStack spacing={4}>
              <Spinner size="lg" color="blue.500" />
              <Text color="gray.600">{loadingMessage}</Text>
            </VStack>
          </Center>
        ) : showEmpty ? (
          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>{emptyText}</AlertDescription>
          </Alert>
        ) : (
          <Box
            borderWidth="1px"
            borderColor="gray.300"
            borderRadius="14px"
            bg="white"
            overflow="hidden"
          >
            {paginationPosition === "top" ? paginationBlock : null}
            {tableBody}
            {paginationPosition === "bottom" ? paginationBlock : null}
          </Box>
        )}
      </VStack>
    </DataTableFilterContext.Provider>
  );
}

/**
 * App-wide declarative data table.
 *
 * - `layout="card"` (default) — read-only or drill-down lists with client sort, chevrons, footers
 * - `layout="admin"` — admin CRUD with search, filters, pagination, and truncated cells
 *
 * Pages own API calls. DataTable owns presentation and emits:
 * `search.onChange`, `filterDefs[].onChange`, `onSortChange`, pagination callbacks, row/action clicks.
 *
 * @example Card layout
 * ```tsx
 * <DataTable
 *   columns={[
 *     { id: "name", header: "Name", sortable: true, sortAccessor: (r) => r.name, cell: (r) => r.name },
 *   ]}
 *   rows={items}
 *   rowKey={(r) => r.id}
 *   onRowClick={openDetail}
 *   showRowChevron
 * />
 * ```
 *
 * @example Admin layout (config-driven search / filters / sort)
 * ```tsx
 * <DataTable
 *   layout="admin"
 *   items={filteredItems}
 *   getRowKey={(r) => r.id}
 *   columns={[
 *     { id: "name", header: "Name", sortable: true, cell: (r) => r.name },
 *     createActionsColumn({ getActions: (r) => [{ id: "view", label: "View", icon: <ViewIcon />, onClick: () => open(r) }] }),
 *   ]}
 *   search={{ value: q, onChange: setQ, placeholder: "Search…", fields: ["name"] }}
 *   filterDefs={[{ id: "status", label: "Status", type: "select", value: status, onChange: setStatus, options: [...] }]}
 *   sort={sort}
 *   onSortChange={setSort}
 * />
 * ```
 */
export function DataTable<T>(props: DataTableProps<T>) {
  if (props.layout === "admin") {
    return <AdminLayoutDataTable {...props} />;
  }
  return <CardLayoutDataTable {...props} />;
}

export default DataTable;
