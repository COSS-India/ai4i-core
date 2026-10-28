import {
  ChevronDownIcon,
  ChevronRightIcon,
  SearchIcon,
} from "@chakra-ui/icons";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  Center,
  Checkbox,
  FormControl,
  FormControlProps,
  HStack,
  FormErrorMessage,
  Input,
  InputGroup,
  InputGroupProps,
  InputLeftElement,
  InputProps,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Portal,
  Select,
  SelectProps,
  Skeleton,
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
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
  ADMIN_CHEVRON_COLUMN_WIDTH,
  DATA_TABLE_CELL_MAX_W,
  TruncatingCellContent,
  getTruncateCellProps,
  cssLengthToPx,
  resolveAdminColumnLayouts,
  shouldAutoTruncateColumn,
  shrinkToContentWidth,
  useContentColumnWidths,
  type AdminColumnLayout,
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
  color: "ink.400",
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
  /** Accessible name for clickable rows; omit when not provided. */
  rowAriaLabel?: (row: T) => string;
  /**
   * Config-driven search input owned by DataTable.
   * Parent performs filtering / API requests via `search.onChange`.
   */
  search?: DataTableSearchConfig;
  /**
   * Config-driven filter controls (`select`, `multiselect`, `text`, `date`).
   * Parent maps values → API via each filter’s `onChange` / `param`.
   * `param` / `search.fields` are documentation for call sites — DataTable does not read them.
   */
  filterDefs?: DataTableFilterDef[];
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
  filterToolbarAlign?: "flex-start" | "center";
  filterToolbarRightContent?: React.ReactNode;
  /**
   * Keep search, filters, and right-side actions on one row from the `md`
   * breakpoint up. Fields shrink to fit; the toolbar scrolls sideways only
   * when they cannot.
   */
  filterToolbarSingleRow?: boolean;
  /**
   * Draw the toolbar as the top of the table surface.
   * Default leaves the toolbar above a separate table card.
   */
  toolbarAttached?: boolean;
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
  /** Replaces the default spinner. Other admin tables keep the spinner when omitted. */
  loadingContent?: React.ReactNode;
  emptyMessage?: string;
  /** Replaces the default empty alert. Other admin tables keep the alert when omitted. */
  emptyContent?: React.ReactNode;
  noResultsMessage?: string;
  unfilteredCount?: number;
  maxHeight?: string;
  tableContainerProps?: Omit<TableContainerProps, "children">;
  size?: "sm" | "md";
  paginationPosition?: "top" | "bottom";
  /** Match card-layout drill-down affordance when rows are clickable. Default: true when `onRowClick` is set. */
  showRowChevron?: boolean;
  /**
   * Rows rendered directly under `row`, with the same columns and a tinted
   * background; return none to show it collapsed. They follow their parent
   * through sort and pagination and don't count as items. `getRowKey` must
   * give each one its own key.
   */
  getSubRows?: (row: T) => readonly T[];
}

export type DataTableProps<T> = DataTableCardProps<T> | DataTableAdminProps<T>;

function buildSortAccessors<T>(
  columns: DataTableColumn<T>[],
): Record<string, (row: T) => string | number> {
  const accessors: Record<string, (row: T) => string | number> = {};
  for (const col of columns) {
    if (!col.sortable) continue;
    accessors[col.id] =
      col.sortAccessor ??
      ((row: T) => {
        const value = (row as Record<string, unknown>)[col.id];
        if (typeof value === "number" || typeof value === "string")
          return value;
        return String(value ?? "");
      });
  }
  return accessors;
}

type DataTableFilterContextValue = {
  resetPage: () => void;
  inputBg: string;
  /**
   * When true (Search applies on submit), changing a filter must not reset the
   * page or trigger a refetch — only Search / Enter / Clear apply.
   */
  deferApply: boolean;
};

const DataTableFilterContext = createContext<DataTableFilterContextValue>({
  resetPage: () => {},
  inputBg: "white",
  deferApply: false,
});

function useDataTableFilterContext() {
  return useContext(DataTableFilterContext);
}

/** Search field wired to reset pagination when the value changes. */
export function TableSearchField({
  label = "Search",
  value,
  onChange,
  onSubmit,
  placeholder,
  helper,
  error,
  hint,
  hideLabel = false,
  debounceMs,
  formControlProps,
  inputGroupProps,
  inputProps,
}: {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  helper?: string;
  error?: string;
  hint?: string;
  hideLabel?: boolean;
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
      // When submit is explicit (Search / Enter), typing alone must not reset the page.
      if (!onSubmit) resetPage();
    },
    [onChange, onSubmit, resetPage],
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
    <FormControl
      w={{ base: "full", md: "320px" }}
      isInvalid={Boolean(error)}
      {...formControlProps}
    >
      <FieldLabel
        hint={hint}
        formLabelProps={hideLabel ? { srOnly: true, mb: 0 } : undefined}
      >
        {label}
      </FieldLabel>
      <InputGroup size="sm" w="full" minW={0} {...inputGroupProps}>
        <InputLeftElement pointerEvents="none">
          <SearchIcon color="gray.400" />
        </InputLeftElement>
        <Input
          minW={0}
          value={localValue}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
          bg={inputBg}
          pl={9}
          aria-label={label}
          aria-invalid={Boolean(error) || undefined}
          {...inputProps}
          onKeyDown={(e) => {
            if (e.key === "Enter" && onSubmit) {
              e.preventDefault();
              if (debounceRef.current) clearTimeout(debounceRef.current);
              onChange(localValue);
              onSubmit();
            }
            inputProps?.onKeyDown?.(e);
          }}
        />
      </InputGroup>
      {error ? (
        <FormErrorMessage fontSize="xs" m={0} mt={1}>
          {error}
        </FormErrorMessage>
      ) : (
        <FieldHint>{helper}</FieldHint>
      )}
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
  error,
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
  /** Marks the field invalid and shows in place of `helper`. */
  error?: string;
  hint?: string;
  inputType?: "text" | "number";
  formControlProps?: FormControlProps;
  inputProps?: Omit<InputProps, "value" | "onChange" | "placeholder" | "type">;
}) {
  const { resetPage, inputBg, deferApply } = useDataTableFilterContext();

  return (
    <FormControl
      w={{ base: "full", sm: "200px" }}
      isInvalid={!!error}
      {...formControlProps}
    >
      <FieldLabel hint={hint}>{label}</FieldLabel>
      <Input
        type={inputType}
        size="sm"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          if (!deferApply) resetPage();
        }}
        placeholder={placeholder}
        bg={inputBg}
        aria-label={label}
        {...inputProps}
      />
      {error ? (
        <FormErrorMessage fontSize="xs" m={0} mt={1}>
          {error}
        </FormErrorMessage>
      ) : (
        <FieldHint>{helper}</FieldHint>
      )}
    </FormControl>
  );
}

/** Date / datetime-local field wired to reset pagination when the value changes. */
export function TableDateField({
  label,
  value,
  onChange,
  onBlur,
  helper,
  hint,
  error,
  inputType = "date",
  formControlProps,
  inputProps,
}: Readonly<{
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** When set, parent can defer applying filters until blur. */
  onBlur?: () => void;
  helper?: string;
  hint?: string;
  error?: string;
  inputType?: "date" | "datetime-local";
  formControlProps?: FormControlProps;
  inputProps?: Omit<InputProps, "value" | "onChange" | "type" | "onBlur">;
}>) {
  const { resetPage, inputBg, deferApply } = useDataTableFilterContext();
  const commitOnChange = !onBlur;

  return (
    <FormControl
      w={{ base: "full", sm: "220px" }}
      isInvalid={Boolean(error)}
      {...formControlProps}
    >
      <FieldLabel hint={hint}>{label}</FieldLabel>
      <Input
        type={inputType}
        size="sm"
        w="full"
        minW={0}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          if (commitOnChange && !deferApply) resetPage();
        }}
        onBlur={() => {
          onBlur?.();
          if (onBlur && !deferApply) resetPage();
        }}
        bg={inputBg}
        aria-label={label}
        fontSize={inputType === "datetime-local" ? "xs" : undefined}
        px={inputType === "datetime-local" ? 2 : undefined}
        sx={{
          minWidth: 0,
          "&::-webkit-datetime-edit": { padding: 0, minWidth: 0 },
          "&::-webkit-calendar-picker-indicator": { margin: 0, padding: 0 },
        }}
        {...inputProps}
      />
      {error ? <FormErrorMessage>{error}</FormErrorMessage> : <FieldHint>{helper}</FieldHint>}
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
  hideLabel = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  helper?: string;
  hint?: string;
  formControlProps?: FormControlProps;
  selectProps?: Omit<SelectProps, "value" | "onChange" | "children">;
  hideLabel?: boolean;
}) {
  const { resetPage, inputBg, deferApply } = useDataTableFilterContext();
  return (
    <FormControl w={{ base: "full", sm: "200px" }} {...formControlProps}>
      <FieldLabel
        hint={hint}
        formLabelProps={hideLabel ? { srOnly: true, mb: 0 } : undefined}
      >
        {label}
      </FieldLabel>
      <Select
        size="sm"
        w="full"
        minW={0}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          if (!deferApply) resetPage();
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

function selectedMultiValues(value: string): Set<string> {
  return new Set(
    value
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean),
  );
}

/** Checkbox menu. Empty value means nothing is selected (parent treats that as all). */
export function TableMultiSelectField({
  label,
  value,
  onChange,
  options,
  helper,
  hint,
  formControlProps,
  hideLabel = false,
  emptyLabel = "All",
}: Readonly<{
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { label: string; value: string }[];
  helper?: string;
  hint?: string;
  formControlProps?: FormControlProps;
  hideLabel?: boolean;
  emptyLabel?: string;
}>) {
  const { resetPage, inputBg, deferApply } = useDataTableFilterContext();
  const selected = selectedMultiValues(value);
  const choices = options.filter((option) => option.value !== "");
  const allLabel =
    options.find((option) => option.value === "")?.label ?? emptyLabel;
  const summary =
    selected.size === 0
      ? allLabel
      : choices
          .filter((option) => selected.has(option.value))
          .map((option) => option.label)
          .join(", ");

  const emit = (next: string) => {
    onChange(next);
    if (!deferApply) resetPage();
  };

  const toggle = (optionValue: string) => {
    if (!optionValue) {
      emit("");
      return;
    }
    const next = selectedMultiValues(value);
    if (next.has(optionValue)) next.delete(optionValue);
    else next.add(optionValue);
    emit(Array.from(next).join(","));
  };

  return (
    <FormControl w={{ base: "full", sm: "200px" }} {...formControlProps}>
      <FieldLabel
        hint={hint}
        formLabelProps={hideLabel ? { srOnly: true, mb: 0 } : undefined}
      >
        {label}
      </FieldLabel>
      <Menu closeOnSelect={false} matchWidth>
        <MenuButton
          as={Button}
          type="button"
          size="sm"
          variant="outline"
          bg={inputBg}
          fontWeight="normal"
          rightIcon={<ChevronDownIcon />}
          w="full"
          textAlign="left"
          justifyContent="space-between"
          aria-label={label}
        >
          <Text as="span" isTruncated display="block" minW={0}>
            {summary || emptyLabel}
          </Text>
        </MenuButton>
        <Portal>
          <MenuList maxH="280px" overflowY="auto" zIndex={20} minW="200px">
            {options.map((option) => {
              const checked =
                option.value === ""
                  ? selected.size === 0
                  : selected.has(option.value);
              return (
                <MenuItem
                  key={option.value || "all"}
                  role="menuitemcheckbox"
                  aria-checked={checked}
                  onClick={() => toggle(option.value)}
                  closeOnSelect={false}
                >
                  <Checkbox
                    isChecked={checked}
                    pointerEvents="none"
                    tabIndex={-1}
                    aria-hidden
                    colorScheme="blue"
                    mr={2}
                  >
                    <Text as="span" fontSize="sm">
                      {option.label}
                    </Text>
                  </Checkbox>
                </MenuItem>
              );
            })}
          </MenuList>
        </Portal>
      </Menu>
      <FieldHint>{helper}</FieldHint>
    </FormControl>
  );
}

function searchControlProps(
  search: DataTableSearchConfig,
): FormControlProps | undefined {
  return sizeControlProps(search);
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
          onSubmit={search.onSubmit}
          placeholder={search.placeholder}
          helper={search.helper}
          hint={search.hint}
          error={search.error}
          hideLabel={search.hideLabel}
          debounceMs={search.debounceMs}
          formControlProps={searchControlProps(search)}
        />
      ) : null}
      {clusteredFilterDefs(filterDefs).map((group) => {
        if (group.defs.length === 1) return renderFilterDef(group.defs[0]);
        return (
          <HStack key={group.key} {...clusterStackProps(group.defs)}>
            {group.defs.map((def) => renderFilterDef(def, CLUSTER_CHILD_PROPS))}
          </HStack>
        );
      })}
    </>
  );
}

/** Start/end pairs split the cluster width instead of keeping their own. */
const CLUSTER_CHILD_PROPS: FormControlProps = {
  flex: "1 1 0",
  minW: 0,
  maxW: "none",
  w: "full",
};

const CLUSTER_GAP_PX = 16;

function clusterStackProps(
  defs: DataTableFilterDef[],
): React.ComponentProps<typeof HStack> {
  const flex = sumClusterFlex(defs);
  if (!flex) {
    return { spacing: 3, align: "flex-start", flexShrink: 0 };
  }
  return {
    spacing: 4,
    align: "flex-start",
    minW: sumClusterSize(defs, "minWidth"),
    maxW: sumClusterSize(defs, "maxWidth"),
    w: { base: "full", md: "auto" },
    flex,
  };
}

function clusteredFilterDefs(
  filterDefs: DataTableFilterDef[] | undefined,
): { key: string; defs: DataTableFilterDef[] }[] {
  const groups: { key: string; defs: DataTableFilterDef[] }[] = [];
  for (const def of filterDefs ?? []) {
    const previous = groups.at(-1);
    if (def.cluster && previous?.key === def.cluster) {
      previous.defs.push(def);
      continue;
    }
    groups.push({ key: def.cluster ?? def.id, defs: [def] });
  }
  return groups;
}

function sizeControlProps(source: {
  width?: string | Record<string, string>;
  minWidth?: string | Record<string, string>;
  maxWidth?: string | Record<string, string>;
  flex?: string | Record<string, string>;
}): FormControlProps | undefined {
  const props: FormControlProps = {};
  if (source.width) props.w = source.width as FormControlProps["w"];
  if (source.minWidth) props.minW = source.minWidth as FormControlProps["minW"];
  if (source.maxWidth) props.maxW = source.maxWidth as FormControlProps["maxW"];
  if (source.flex) props.flex = source.flex as FormControlProps["flex"];
  return Object.keys(props).length > 0 ? props : undefined;
}

function filterWidthProps(
  def: DataTableFilterDef,
): FormControlProps | undefined {
  return sizeControlProps(def);
}

type CssSizeToken = string | Record<string, string>;

function cssTokenString(value: CssSizeToken): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function cssTokenAt(
  value: CssSizeToken,
  breakpoint: string,
): string | undefined {
  return typeof value === "string" ? value : value[breakpoint];
}

function collectBreakpoints(values: CssSizeToken[]): string[] {
  const breakpoints = new Set<string>();
  for (const value of values) {
    if (typeof value === "object") {
      Object.keys(value).forEach((key) => breakpoints.add(key));
    }
  }
  return Array.from(breakpoints);
}

function parseFlexParts(value: string): { grow: number; basis: number; percent: boolean } {
  const parts = value.trim().split(/\s+/);
  const basis = parts[2] ?? "0";
  return {
    grow: Number(parts[0]) || 0,
    basis: Number.parseFloat(basis) || 0,
    percent: basis.includes("%"),
  };
}

function sumParsedFlex(
  parsed: ReturnType<typeof parseFlexParts>[],
): string {
  if (parsed.some((part) => part.percent)) return "1 1 100%";
  const grow = parsed.reduce((sum, part) => sum + part.grow, 0);
  const basis = parsed.reduce((sum, part) => sum + part.basis, 0) + CLUSTER_GAP_PX;
  return `${grow} 1 ${basis}px`;
}

function sumClusterFlex(
  defs: DataTableFilterDef[],
): FormControlProps["flex"] | undefined {
  const values = defs
    .map((def) => def.flex)
    .filter((value): value is NonNullable<DataTableFilterDef["flex"]> => value != null);
  if (values.length === 0) return undefined;

  const breakpoints = collectBreakpoints(values);
  if (breakpoints.length === 0) {
    const parsed = values
      .map(cssTokenString)
      .filter((token): token is string => token != null)
      .map(parseFlexParts);
    return sumParsedFlex(parsed);
  }

  const result: Record<string, string> = {};
  for (const breakpoint of breakpoints) {
    const parsed = values
      .map((value) => {
        const raw = cssTokenAt(value, breakpoint);
        return raw ? parseFlexParts(raw) : null;
      })
      .filter((part): part is NonNullable<typeof part> => part != null);
    result[breakpoint] = sumParsedFlex(parsed);
  }
  return result;
}

function sumPxTokens(values: CssSizeToken[]): number {
  return values.reduce((sum, value) => {
    const token = cssTokenString(value);
    return sum + (token ? Number.parseFloat(token) || 0 : 0);
  }, 0);
}

function sumPxAtBreakpoint(
  values: CssSizeToken[],
  breakpoint: string,
): number | undefined {
  let px = 0;
  for (const value of values) {
    const raw = cssTokenAt(value, breakpoint);
    if (!raw || Number.isNaN(Number.parseFloat(raw))) return undefined;
    px += Number.parseFloat(raw);
  }
  return px;
}

function sumClusterSize(
  defs: DataTableFilterDef[],
  key: "minWidth" | "maxWidth",
): FormControlProps["minW"] | undefined {
  const values = defs
    .map((def) => def[key])
    .filter((value): value is NonNullable<DataTableFilterDef["minWidth"]> => value != null);
  if (values.length === 0) return undefined;

  const breakpoints = collectBreakpoints(values);
  const addGap = (px: number) => `${px + (defs.length - 1) * CLUSTER_GAP_PX}px`;
  if (breakpoints.length === 0) return addGap(sumPxTokens(values));

  const result: Record<string, string> = {};
  for (const breakpoint of breakpoints) {
    const px = sumPxAtBreakpoint(values, breakpoint);
    if (px != null) result[breakpoint] = addGap(px);
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

function renderSelectFilterDef(
  def: DataTableFilterDef,
  formControlProps?: FormControlProps,
): React.ReactNode {
  return (
    <TableSelectField
      key={def.id}
      label={def.label}
      value={def.value}
      onChange={def.onChange}
      helper={def.helper}
      hint={def.hint}
      hideLabel={def.hideLabel}
      formControlProps={formControlProps ?? filterWidthProps(def)}
    >
      {(def.options ?? []).map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </TableSelectField>
  );
}

function renderMultiSelectFilterDef(
  def: DataTableFilterDef,
  formControlProps?: FormControlProps,
): React.ReactNode {
  return (
    <TableMultiSelectField
      key={def.id}
      label={def.label}
      value={def.value}
      onChange={def.onChange}
      options={def.options ?? []}
      helper={def.helper}
      hint={def.hint}
      hideLabel={def.hideLabel}
      formControlProps={formControlProps ?? filterWidthProps(def)}
    />
  );
}

function renderTextFilterDef(
  def: DataTableFilterDef,
  formControlProps?: FormControlProps,
): React.ReactNode {
  const textType = def.inputType === "number" ? "number" : "text";
  return (
    <TableTextField
      key={def.id}
      label={def.label}
      value={def.value}
      onChange={def.onChange}
      placeholder={def.placeholder}
      helper={def.helper}
      hint={def.hint}
      error={def.error}
      inputType={textType}
      formControlProps={formControlProps ?? filterWidthProps(def)}
      inputProps={textType === "number" ? { min: 0 } : undefined}
    />
  );
}

function renderDateFilterDef(
  def: DataTableFilterDef,
  formControlProps?: FormControlProps,
): React.ReactNode {
  const dateType =
    def.inputType === "datetime-local" ? "datetime-local" : "date";
  return (
    <TableDateField
      key={def.id}
      label={def.label}
      value={def.value}
      onChange={def.onChange}
      onBlur={def.onBlur}
      helper={def.helper}
      hint={def.hint}
      error={def.error}
      inputType={dateType}
      formControlProps={formControlProps ?? filterWidthProps(def)}
    />
  );
}

function renderFilterDef(
  def: DataTableFilterDef,
  formControlProps?: FormControlProps,
): React.ReactNode {
  if (def.type === "select") return renderSelectFilterDef(def, formControlProps);
  if (def.type === "multiselect") return renderMultiSelectFilterDef(def, formControlProps);
  if (def.type === "text") return renderTextFilterDef(def, formControlProps);
  if (def.type === "date") return renderDateFilterDef(def, formControlProps);

  if (process.env.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.warn(
      `[DataTable] filterDefs type "${def.type}" is not rendered yet (id="${def.id}").`,
    );
  }
  return null;
}

function AdminSortableHeader<T>({
  col,
  sort,
  onSortChange,
}: Readonly<{
  col: DataTableColumn<T>;
  sort?: DataTableSortState;
  onSortChange?: (next: DataTableSortState) => void;
}>) {
  const hint = columnHint(col);

  if (col.sortable && onSortChange) {
    const key = columnSortKey(col);
    const labelText =
      typeof col.header === "string" ? col.header : String(col.header ?? key);
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
      <FieldLabel variant="header" hint={hint} align={col.align ?? "left"}>
        {col.header}
      </FieldLabel>
    );
  }

  return <>{col.header}</>;
}

function columnHeaderSx<T>(col: DataTableColumn<T>) {
  return {
    ...DATA_TABLE_HEADER_SX,
    ...(col.isNumeric || col.align === "right"
      ? { textAlign: "right" as const }
      : {}),
    ...(col.align === "center" ? { textAlign: "center" as const } : {}),
  };
}

function renderCardColumnHeader<T>(
  col: DataTableColumn<T>,
  options: {
    sortingEnabled: boolean;
    activeSortKey: string;
    activeSortDirection: DataTableSortState["direction"];
    onSortChange: (next: DataTableSortState) => void;
  },
): React.ReactNode {
  if (options.sortingEnabled && col.sortable) {
    return (
      <AdminSortableHeader
        col={col}
        sort={{
          key: options.activeSortKey,
          direction: options.activeSortDirection,
        }}
        onSortChange={options.onSortChange}
      />
    );
  }
  const hint = columnHint(col);
  if (hint) {
    return (
      <FieldLabel variant="header" hint={hint} align={col.align ?? "left"}>
        {col.header}
      </FieldLabel>
    );
  }
  return col.header;
}

function cardLayoutDefaults(variant: DataTableCardProps<unknown>["variant"]) {
  const compact = variant === "compact";
  return {
    borderRadius: compact ? "10px" : "14px",
    cellPy: compact ? 3 : 4,
    containerMt: compact ? 0 : 1,
  } as const;
}

function CardLayoutDataRow<T>({
  row,
  index,
  columns,
  cellPy,
  clickable,
  onRowClick,
  rowAriaLabel,
  showRowChevron,
  renderAfterRow,
}: Readonly<{
  row: T;
  index: number;
  columns: DataTableColumn<T>[];
  cellPy: number | string;
  clickable: boolean;
  onRowClick?: (row: T) => void;
  rowAriaLabel?: (row: T) => string;
  showRowChevron: boolean;
  renderAfterRow?: (row: T) => React.ReactNode;
}>) {
  const rowProps = clickable
    ? {
        tabIndex: 0,
        "aria-label": rowAriaLabel?.(row) ?? "View details",
        cursor: "pointer" as const,
        _hover: {
          bg: "#FAFBFE",
          "& .data-table-chevron": { color: "ink.600" },
        },
        onClick: () => onRowClick?.(row),
        onKeyDown: (e: React.KeyboardEvent) => {
          // Only activate the row when the row itself is focused — not nested
          // controls (actions, checkboxes, links).
          if (e.target !== e.currentTarget) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onRowClick?.(row);
          }
        },
      }
    : {};

  return (
    <>
      <Tr {...rowProps}>
        {columns.map((col) => (
          <Td
            key={col.id}
            py={cellPy}
            isNumeric={col.isNumeric}
            textAlign={col.align}
            w={shrinkToContentWidth(col)}
            minW={col.minWidth}
            whiteSpace={shouldAutoTruncateColumn(col) ? undefined : "nowrap"}
          >
            {col.cell(row, index)}
          </Td>
        ))}
        {showRowChevron ? (
          <Td py={cellPy} textAlign="right">
            <ChevronRightIcon
              className="data-table-chevron"
              boxSize={3.5}
              color="ink.400"
            />
          </Td>
        ) : null}
      </Tr>
      {renderAfterRow?.(row) ?? null}
    </>
  );
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
  borderRadius,
  theadBg = "ink.50",
  cellPy,
  tableMinWidth,
  containerMt,
  tableProps,
}: Readonly<DataTableCardProps<T>>) {
  const defaults = cardLayoutDefaults(variant);
  const resolvedBorderRadius = borderRadius ?? defaults.borderRadius;
  const resolvedCellPy = cellPy ?? defaults.cellPy;
  const resolvedContainerMt = containerMt ?? defaults.containerMt;
  const sortAccessors = useMemo(() => buildSortAccessors(columns), [columns]);
  const initialSortKey =
    defaultSortKey ??
    columns.find((c) => c.sortable)?.id ??
    columns[0]?.id ??
    "";
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

  const displayRows =
    sortingEnabled && !parentOwnsSort ? sortedRows : [...rows];
  const hasFooter = showFooter && columns.some((c) => c.footer != null);
  const clickable = Boolean(onRowClick);

  const table = (
    <Box
      overflowX="auto"
      mt={resolvedContainerMt}
      borderWidth="1px"
      borderColor="ink.200"
      borderRadius={resolvedBorderRadius}
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
            {columns.map((col) => (
                <Th
                  key={col.id}
                  w={shrinkToContentWidth(col)}
                  minW={col.minWidth}
                  isNumeric={col.isNumeric}
                  sx={columnHeaderSx(col)}
                  whiteSpace={
                    shouldAutoTruncateColumn(col) ? undefined : "nowrap"
                  }
                >
                  {renderCardColumnHeader(col, {
                    sortingEnabled,
                    activeSortKey,
                    activeSortDirection,
                    onSortChange: handleSortChange,
                  })}
                </Th>
            ))}
            {showRowChevron ? (
              <Th w="4%" borderBottomWidth="1px" sx={DATA_TABLE_HEADER_SX} />
            ) : null}
          </Tr>
        </Thead>
        <Tbody>
          {displayRows.map((row, index) => (
            <CardLayoutDataRow
              key={rowKey(row)}
              row={row}
              index={index}
              columns={columns}
              cellPy={resolvedCellPy}
              clickable={clickable}
              onRowClick={onRowClick}
              rowAriaLabel={rowAriaLabel}
              showRowChevron={showRowChevron}
              renderAfterRow={renderAfterRow}
            />
          ))}
          {hasFooter ? (
            <Tr bg={theadBg}>
              {columns.map((col) => (
                <Td
                  key={col.id}
                  py={resolvedCellPy}
                  fontWeight="extrabold"
                  fontSize="13px"
                  color="gray.800"
                >
                  {col.footer ?? null}
                </Td>
              ))}
              {showRowChevron ? <Td py={resolvedCellPy} /> : null}
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
        <Spinner size="lg" color="ink.600" />
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
        <Text color="ink.500">{emptyMessage}</Text>
      </Center>
    );
  }

  return table;
}

type AdminPaginationControls = {
  startRow: number;
  endRow: number;
  totalItems: number;
  page: number;
  totalPages: number;
  pageSize: number;
  pageSizeOptions: number[];
  onPageSizeChange: (size: number) => void;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  onLast: () => void;
  canPrev: boolean;
  canNext: boolean;
  resetPage: () => void;
};

function buildClientAdminPagination(
  clientTable: ReturnType<typeof useAdminDataTable>,
): AdminPaginationControls {
  return {
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
    onNext: () =>
      clientTable.setPage((p) => Math.min(clientTable.totalPages, p + 1)),
    onLast: () => clientTable.setPage(clientTable.totalPages),
    canPrev: clientTable.canPrev,
    canNext: clientTable.canNext,
    resetPage: clientTable.resetPage,
  };
}

function buildServerAdminPagination(
  serverTable: ReturnType<typeof useAdminDataTableServer>,
  onPageChange: (page: number) => void,
): AdminPaginationControls {
  return {
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
    resetPage: () => onPageChange(1),
  };
}

function resolveAdminPagination(
  paginate: DataTableAdminProps<unknown>["paginate"],
  clientTable: ReturnType<typeof useAdminDataTable>,
  serverTable: ReturnType<typeof useAdminDataTableServer>,
  serverPagination: UseAdminDataTableServerOptions | undefined,
): AdminPaginationControls | null {
  if (paginate === "client") {
    return buildClientAdminPagination(clientTable);
  }
  if (paginate === "server" && serverPagination) {
    return buildServerAdminPagination(
      serverTable,
      serverPagination.onPageChange,
    );
  }
  return null;
}

function resolveAdminShowEmpty(options: {
  isLoading: boolean;
  paginate: DataTableAdminProps<unknown>["paginate"];
  serverTotalItems: number;
  clientTotalItems: number;
  itemCount: number;
}): boolean {
  if (options.isLoading) return false;
  if (options.paginate === "server") return options.serverTotalItems === 0;
  if (options.paginate === "client") return options.clientTotalItems === 0;
  return options.itemCount === 0;
}

function resolveAdminEmptyText(options: {
  hasActiveFilters: boolean;
  unfilteredCount?: number;
  noResultsMessage: string;
  emptyMessage: string;
}): string {
  if (options.hasActiveFilters) return options.noResultsMessage;
  if (options.unfilteredCount != null && options.unfilteredCount > 0) {
    return options.noResultsMessage;
  }
  return options.emptyMessage;
}

type AdminTableLoadingBodyProps<T> = Readonly<{
  columns: DataTableColumn<T>[];
  columnCount: number;
  rowChevron: boolean;
  loadingContent?: React.ReactNode;
}>;

function AdminTableLoadingBody<T>({
  columns,
  columnCount,
  rowChevron,
  loadingContent,
}: AdminTableLoadingBodyProps<T>): React.ReactElement {
  if (loadingContent) {
    return (
      <Tr>
        <Td colSpan={columnCount} py={0} px={0} borderBottomWidth={0}>
          {loadingContent}
        </Td>
      </Tr>
    );
  }
  return (
    <>
      {Array.from({ length: 5 }, (_, rowIndex) => (
        <Tr key={`loading-${rowIndex}`}>
          {columns.map((col) => (
            <Td key={col.id} py={4}>
              <Skeleton h="14px" borderRadius="sm" />
            </Td>
          ))}
          {rowChevron ? (
            <Td
              w={ADMIN_CHEVRON_COLUMN_WIDTH}
              minW={ADMIN_CHEVRON_COLUMN_WIDTH}
              maxW={ADMIN_CHEVRON_COLUMN_WIDTH}
              px={1}
              py={4}
              whiteSpace="nowrap"
            />
          ) : null}
        </Tr>
      ))}
    </>
  );
}

type AdminTableEmptyBodyProps = Readonly<{
  columnCount: number;
  emptyContent?: React.ReactNode;
  emptyText: string;
}>;

function AdminTableEmptyBody({
  columnCount,
  emptyContent,
  emptyText,
}: AdminTableEmptyBodyProps): React.ReactElement {
  return (
    <Tr>
      <Td colSpan={columnCount} py={6} overflow="visible">
        {emptyContent ?? (
          <Alert status="info" borderRadius="md">
            <AlertIcon />
            <AlertDescription>{emptyText}</AlertDescription>
          </Alert>
        )}
      </Td>
    </Tr>
  );
}

type AdminTableDataBodyProps<T> = Readonly<{
  displayItems: T[];
  columns: DataTableColumn<T>[];
  columnLayouts: ReturnType<typeof resolveAdminColumnLayouts>;
  getRowKey: (row: T) => string;
  getSubRows?: (row: T) => readonly T[];
  onRowClick?: (row: T) => void;
  rowAriaLabel?: (row: T) => string;
  rowChevron: boolean;
}>;

function renderAdminDataCell<T>(
  col: DataTableColumn<T>,
  row: T,
  parentIndex: number,
  layout: AdminColumnLayout,
): React.ReactElement {
  const truncate = shouldAutoTruncateColumn(col);
  const content = col.cell(row, parentIndex);
  const numeric = Boolean(
    col.isNumeric || col.align === "center" || col.align === "right",
  );
  return (
    <Td
      key={col.id}
      py={4}
      isNumeric={col.isNumeric}
      textAlign={col.align}
      w={layout.w}
      minW={layout.minW}
      maxW={layout.maxW}
      whiteSpace={layout.whiteSpace}
      sx={numeric ? { fontVariantNumeric: "tabular-nums" } : undefined}
      {...(col.tdProps ?? {})}
      overflow="hidden"
    >
      <TruncatingCellContent ellipsis={truncate}>{content}</TruncatingCellContent>
    </Td>
  );
}

function adminRowKeyDownHandler<T>(
  onRowClick: ((row: T) => void) | undefined,
  row: T,
): ((e: React.KeyboardEvent) => void) | undefined {
  if (!onRowClick) return undefined;
  return (e: React.KeyboardEvent) => {
    // Nested controls (actions, links) own Enter/Space; only the row itself opens.
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onRowClick(row);
    }
  };
}

function AdminRowChevronCell(): React.ReactElement {
  return (
    <Td
      w={ADMIN_CHEVRON_COLUMN_WIDTH}
      minW={ADMIN_CHEVRON_COLUMN_WIDTH}
      maxW={ADMIN_CHEVRON_COLUMN_WIDTH}
      px={1}
      py={4}
      textAlign="right"
      whiteSpace="nowrap"
    >
      <ChevronRightIcon
        className="data-table-chevron"
        boxSize={3.5}
        color="ink.400"
      />
    </Td>
  );
}

function AdminTableDataRow<T>({
  row,
  parentIndex,
  isSubRow,
  columns,
  columnLayouts,
  getRowKey,
  onRowClick,
  rowAriaLabel,
  rowChevron,
}: Readonly<{
  row: T;
  parentIndex: number;
  isSubRow: boolean;
  columns: DataTableColumn<T>[];
  columnLayouts: ReturnType<typeof resolveAdminColumnLayouts>;
  getRowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  rowAriaLabel?: (row: T) => string;
  rowChevron: boolean;
}>): React.ReactElement {
  const clickable = Boolean(onRowClick);
  return (
    <Tr
      key={getRowKey(row)}
      tabIndex={clickable ? 0 : undefined}
      aria-label={clickable ? rowAriaLabel?.(row) : undefined}
      onClick={clickable ? () => onRowClick?.(row) : undefined}
      onKeyDown={adminRowKeyDownHandler(onRowClick, row)}
      cursor={clickable ? "pointer" : undefined}
      bg={isSubRow ? "ink.50" : undefined}
      _hover={{
        bg: "#FAFBFE",
        ...(rowChevron ? { "& .data-table-chevron": { color: "ink.600" } } : {}),
      }}
      transition="background 0.15s"
    >
      {columns.map((col) =>
        renderAdminDataCell(
          col,
          row,
          parentIndex,
          columnLayouts.get(col.id) ?? { minW: 0 },
        ),
      )}
      {rowChevron ? <AdminRowChevronCell /> : null}
    </Tr>
  );
}

function AdminTableDataBody<T>({
  displayItems,
  columns,
  columnLayouts,
  getRowKey,
  getSubRows,
  onRowClick,
  rowAriaLabel,
  rowChevron,
}: AdminTableDataBodyProps<T>): React.ReactElement {
  return (
    <>
      {displayItems.flatMap((parent, parentIndex) =>
        [parent, ...(getSubRows?.(parent) ?? [])].map((row, subIndex) => (
          <AdminTableDataRow
            key={getRowKey(row)}
            row={row}
            parentIndex={parentIndex}
            isSubRow={subIndex > 0}
            columns={columns}
            columnLayouts={columnLayouts}
            getRowKey={getRowKey}
            onRowClick={onRowClick}
            rowAriaLabel={rowAriaLabel}
            rowChevron={rowChevron}
          />
        )),
      )}
    </>
  );
}

function renderAdminTableBody<T>(options: {
  isLoading: boolean;
  showEmpty: boolean;
  loadingContent?: React.ReactNode;
  emptyContent?: React.ReactNode;
  emptyText: string;
  columns: DataTableColumn<T>[];
  columnCount: number;
  columnLayouts: ReturnType<typeof resolveAdminColumnLayouts>;
  displayItems: T[];
  getRowKey: (row: T) => string;
  getSubRows?: (row: T) => readonly T[];
  onRowClick?: (row: T) => void;
  rowAriaLabel?: (row: T) => string;
  rowChevron: boolean;
}): React.ReactNode {
  if (options.isLoading) {
    return (
      <AdminTableLoadingBody
        columns={options.columns}
        columnCount={options.columnCount}
        rowChevron={options.rowChevron}
        loadingContent={options.loadingContent}
      />
    );
  }
  if (options.showEmpty) {
    return (
      <AdminTableEmptyBody
        columnCount={options.columnCount}
        emptyContent={options.emptyContent}
        emptyText={options.emptyText}
      />
    );
  }
  return (
    <AdminTableDataBody
      displayItems={options.displayItems}
      columns={options.columns}
      columnLayouts={options.columnLayouts}
      getRowKey={options.getRowKey}
      getSubRows={options.getSubRows}
      onRowClick={options.onRowClick}
      rowAriaLabel={options.rowAriaLabel}
      rowChevron={options.rowChevron}
    />
  );
}

function AdminTableHead<T>({
  columns,
  columnLayouts,
  sort,
  onSortChange,
  rowChevron,
}: Readonly<{
  columns: DataTableColumn<T>[];
  columnLayouts: ReturnType<typeof resolveAdminColumnLayouts>;
  sort?: DataTableSortState;
  onSortChange?: (next: DataTableSortState) => void;
  rowChevron: boolean;
}>): React.ReactElement {
  return (
    <Thead bg="ink.50" position="sticky" top={0} zIndex={1}>
      <Tr>
        {columns.map((col) => {
          const layout = columnLayouts.get(col.id) ?? { minW: 0 };
          return (
            <Th
              key={col.id}
              py={3}
              overflow={layout.whiteSpace === "nowrap" ? "visible" : "hidden"}
              w={layout.w}
              minW={layout.minW}
              maxW={layout.maxW}
              whiteSpace={layout.whiteSpace}
              sx={columnHeaderSx(col)}
              {...(col.thProps ?? {})}
            >
              <AdminSortableHeader
                col={col}
                sort={sort}
                onSortChange={onSortChange}
              />
            </Th>
          );
        })}
        {rowChevron ? (
          <Th
            w={ADMIN_CHEVRON_COLUMN_WIDTH}
            minW={ADMIN_CHEVRON_COLUMN_WIDTH}
            maxW={ADMIN_CHEVRON_COLUMN_WIDTH}
            px={1}
            py={3}
            whiteSpace="nowrap"
            sx={DATA_TABLE_HEADER_SX}
          />
        ) : null}
      </Tr>
    </Thead>
  );
}

function buildAdminPaginationBlock(
  pagination: AdminPaginationControls | null,
  paginate: DataTableAdminProps<unknown>["paginate"],
  paginationPosition: "top" | "bottom",
): React.ReactNode {
  if (paginate === false || !pagination || pagination.totalItems <= 0) {
    return null;
  }
  return (
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
      borderColor="ink.200"
      bg="ink.50"
      variant="attached"
      placement={paginationPosition}
    />
  );
}

function AdminFilterToolbarSection({
  search,
  filterDefs,
  hasActiveFilters,
  onClear,
  filterToolbarAlign,
  filterToolbarRightContent,
  filterToolbarSingleRow = false,
  toolbarAttached,
  showFiltersHeading,
  filtersHeading,
  toolbarLabelsVisible,
}: Readonly<{
  search?: DataTableSearchConfig;
  filterDefs?: DataTableFilterDef[];
  hasActiveFilters: boolean;
  onClear?: () => void;
  filterToolbarAlign: "flex-start" | "center";
  filterToolbarRightContent?: React.ReactNode;
  filterToolbarSingleRow: boolean;
  toolbarAttached: boolean;
  showFiltersHeading: boolean;
  filtersHeading: string;
  toolbarLabelsVisible: boolean;
}>): React.ReactElement | null {
  if (!search && !(filterDefs && filterDefs.length > 0)) {
    return null;
  }
  return (
    <Box
      px={toolbarAttached ? 4 : 0}
      py={toolbarAttached ? 3 : 0}
      borderBottomWidth={toolbarAttached ? "1px" : 0}
      borderColor="ink.100"
      minW={0}
      w="full"
      overflowX={filterToolbarSingleRow ? "auto" : undefined}
    >
      <VStack spacing={4} align="stretch">
        {showFiltersHeading ? (
          <Text
            fontSize="sm"
            fontWeight="semibold"
            color="gray.700"
            userSelect="none"
          >
            {filtersHeading}
          </Text>
        ) : null}
        <TableFilterToolbar
          hasActiveFilters={hasActiveFilters}
          onClear={onClear}
          align={filterToolbarAlign}
          alignActionsToInputs={toolbarLabelsVisible}
          rightContent={filterToolbarRightContent}
          spacing={filterToolbarSingleRow ? 4 : 3}
          flexWrap={filterToolbarSingleRow ? { base: "wrap", md: "nowrap" } : "wrap"}
        >
          <ConfigDrivenFilters search={search} filterDefs={filterDefs} />
        </TableFilterToolbar>
      </VStack>
    </Box>
  );
}

function AdminTableSurface({
  toolbarAttached,
  showPagination,
  paginationPosition,
  paginationBlock,
  tableBody,
}: Readonly<{
  toolbarAttached: boolean;
  showPagination: boolean;
  paginationPosition: "top" | "bottom";
  paginationBlock: React.ReactNode;
  tableBody: React.ReactNode;
}>): React.ReactElement {
  const showTop = showPagination && paginationPosition === "top";
  const showBottom = showPagination && paginationPosition === "bottom";
  return (
    <Box
      w="full"
      minW={0}
      borderWidth={toolbarAttached ? 0 : "1px"}
      borderColor="ink.200"
      borderRadius={toolbarAttached ? 0 : "14px"}
      bg="white"
      overflow="hidden"
    >
      {showTop ? paginationBlock : null}
      {tableBody}
      {showBottom ? paginationBlock : null}
    </Box>
  );
}

function AdminTableFrame({
  toolbarAttached,
  toolbar,
  tableSurface,
  filterContextValue,
}: Readonly<{
  toolbarAttached: boolean;
  toolbar: React.ReactNode;
  tableSurface: React.ReactNode;
  filterContextValue: {
    resetPage: () => void;
    inputBg: string;
    deferApply: boolean;
  };
}>): React.ReactElement {
  const stack = (
    <VStack spacing={toolbarAttached ? 0 : 6} align="stretch" w="full" minW={0}>
      {toolbar}
      {tableSurface}
    </VStack>
  );
  const content = toolbarAttached ? (
    <Box
      w="full"
      minW={0}
      borderWidth="1px"
      borderColor="ink.200"
      borderRadius="lg"
      bg="white"
      overflow="hidden"
    >
      {stack}
    </Box>
  ) : (
    stack
  );
  return (
    <DataTableFilterContext.Provider value={filterContextValue}>
      {content}
    </DataTableFilterContext.Provider>
  );
}

function stripAdminTableContainerChrome(
  tableContainerProps: Omit<TableContainerProps, "children"> | undefined,
): {
  containerMaxH: TableContainerProps["maxH"];
  restTableContainerProps: Omit<TableContainerProps, "children">;
} {
  const {
    borderWidth: _borderWidth,
    borderColor: _borderColor,
    borderRadius: _borderRadius,
    bg: _bg,
    overflow: _overflow,
    overflowX: _overflowX,
    overflowY: _overflowY,
    maxH: containerMaxH,
    ...restTableContainerProps
  } = tableContainerProps ?? {};
  return { containerMaxH, restTableContainerProps };
}

function AdminLayoutDataTable<T>(props: Readonly<DataTableAdminProps<T>>) {
  const {
    items,
    columns,
    getRowKey,
    search,
    filterDefs,
    hasActiveFilters = false,
    onClearFilters,
    filterToolbarAlign = "flex-start",
    filterToolbarRightContent,
    filterToolbarSingleRow = false,
    toolbarAttached = false,
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
    loadingContent,
    emptyMessage = "No items found.",
    emptyContent,
    noResultsMessage = "No items match the current filters.",
    unfilteredCount,
    onRowClick,
    rowAriaLabel,
    maxHeight = "60vh",
    tableContainerProps,
    size = "sm",
    paginationPosition = "bottom",
    showRowChevron,
    getSubRows,
  } = props;

  const { cardBg } = useAdminTableSurface();
  const rowChevron = showRowChevron ?? Boolean(onRowClick);
  const fallbackColumnLayouts = useMemo(
    () => resolveAdminColumnLayouts(columns),
    [columns],
  );
  const tableRef = useRef<HTMLTableElement>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);

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

  const displayItems =
    paginate === "client" ? clientTable.paginatedItems : items;

  const measuredWidths = useContentColumnWidths({
    tableRef,
    containerRef: tableContainerRef,
    columns,
    trailingFixedPx: rowChevron ? cssLengthToPx(ADMIN_CHEVRON_COLUMN_WIDTH) : undefined,
    enabled: !isLoading,
    contentKey: displayItems,
  });
  /** Once measured, `<colgroup>` owns widths; cells keep only wrapping rules. */
  const columnLayouts = useMemo(() => {
    if (!measuredWidths) return fallbackColumnLayouts;
    const stripped = new Map<string, AdminColumnLayout>();
    fallbackColumnLayouts.forEach((layout, id) => {
      stripped.set(id, { minW: 0, whiteSpace: layout.whiteSpace });
    });
    return stripped;
  }, [measuredWidths, fallbackColumnLayouts]);
  const pagination = resolveAdminPagination(
    paginate,
    clientTable,
    serverTable,
    serverPagination,
  );

  const handleClearFilters = useCallback(() => {
    onClearFilters?.();
    pagination?.resetPage();
  }, [onClearFilters, pagination?.resetPage]);

  const deferApply = Boolean(search?.onSubmit);
  const filterContextValue = useMemo(
    () => ({
      resetPage: pagination?.resetPage ?? (() => {}),
      inputBg: cardBg,
      deferApply,
    }),
    [pagination?.resetPage, cardBg, deferApply],
  );

  const showEmpty = resolveAdminShowEmpty({
    isLoading,
    paginate,
    serverTotalItems: serverPagination?.totalItems ?? 0,
    clientTotalItems: clientTable.totalItems,
    itemCount: items.length,
  });
  const emptyText = resolveAdminEmptyText({
    hasActiveFilters,
    unfilteredCount,
    noResultsMessage,
    emptyMessage,
  });
  const paginationBlock = buildAdminPaginationBlock(
    pagination,
    paginate,
    paginationPosition,
  );
  const toolbarLabelsVisible =
    Boolean(search && !search.hideLabel) ||
    (filterDefs ?? []).some((def) => !def.hideLabel);
  const { containerMaxH, restTableContainerProps } =
    stripAdminTableContainerChrome(tableContainerProps);
  const columnCount = columns.length + (rowChevron ? 1 : 0);

  const tableBody = (
    <TableContainer
      ref={tableContainerRef}
      maxH={containerMaxH ?? maxHeight}
      overflowY="auto"
      overflowX="auto"
      bg="white"
      sx={{ scrollbarGutter: "stable" }}
      {...restTableContainerProps}
    >
      <Table
        ref={tableRef}
        variant="simple"
        bg="white"
        size={size}
        w="100%"
        aria-busy={isLoading || undefined}
        aria-label={isLoading ? loadingMessage : undefined}
        sx={{
          tableLayout: "fixed",
          width: "100%",
          "th, td": { verticalAlign: "middle" },
        }}
      >
        {measuredWidths ? (
          <colgroup>
            {measuredWidths.map((width, i) => {
              const colKey =
                i < columns.length ? columns[i].id : "row-chevron";
              return (
                <col key={colKey} style={{ width: `${width}px` }} />
              );
            })}
          </colgroup>
        ) : null}
        <AdminTableHead
          columns={columns}
          columnLayouts={columnLayouts}
          sort={sort}
          onSortChange={onSortChange}
          rowChevron={rowChevron}
        />
        <Tbody>
          {renderAdminTableBody({
            isLoading,
            showEmpty,
            loadingContent,
            emptyContent,
            emptyText,
            columns,
            columnCount,
            columnLayouts,
            displayItems,
            getRowKey,
            getSubRows,
            onRowClick,
            rowAriaLabel,
            rowChevron,
          })}
        </Tbody>
      </Table>
    </TableContainer>
  );

  const toolbar = (
    <AdminFilterToolbarSection
      search={search}
      filterDefs={filterDefs}
      hasActiveFilters={hasActiveFilters}
      onClear={onClearFilters ? handleClearFilters : undefined}
      filterToolbarAlign={filterToolbarAlign}
      filterToolbarRightContent={filterToolbarRightContent}
      filterToolbarSingleRow={filterToolbarSingleRow}
      toolbarAttached={toolbarAttached}
      showFiltersHeading={showFiltersHeading}
      filtersHeading={filtersHeading}
      toolbarLabelsVisible={toolbarLabelsVisible}
    />
  );

  const tableSurface = (
    <AdminTableSurface
      toolbarAttached={toolbarAttached}
      showPagination={!isLoading && !showEmpty}
      paginationPosition={paginationPosition}
      paginationBlock={paginationBlock}
      tableBody={tableBody}
    />
  );

  return (
    <AdminTableFrame
      toolbarAttached={toolbarAttached}
      toolbar={toolbar}
      tableSurface={tableSurface}
      filterContextValue={filterContextValue}
    />
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
 *     createActionsColumn({ actionCount: 2, getActions: (r) => [
 *       { id: "edit", label: "Edit", onClick: () => edit(r) },
 *       { id: "delete", label: "Delete", onClick: () => remove(r) },
 *     ]}),
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
