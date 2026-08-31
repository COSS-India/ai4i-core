import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Center,
  FormControl,
  FormControlProps,
  FormLabel,
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
  Tooltip,
  Tr,
  VStack,
} from "@chakra-ui/react";
import { SearchIcon } from "@chakra-ui/icons";
import FieldHint from "./FieldHint";
import {
  TableFilterToolbar,
  TablePaginationBar,
  TableSortHeader,
  useAdminTableSurface,
} from "./TableControls";
import {
  DEFAULT_PAGE_SIZE_OPTIONS,
  useAdminDataTable,
  useAdminDataTableServer,
  type UseAdminDataTableServerOptions,
} from "../../hooks/useAdminDataTable";

export { DEFAULT_PAGE_SIZE_OPTIONS } from "../../hooks/useAdminDataTable";
export { useAdminDataTable, useAdminDataTableServer } from "../../hooks/useAdminDataTable";

type SortDirection = "asc" | "desc";

/** Default max width for truncated admin table cells. */
export const ADMIN_TABLE_CELL_MAX_W = "280px";

const DEFAULT_TRUNCATE_CELL_PROPS: TableCellProps = {
  maxW: ADMIN_TABLE_CELL_MAX_W,
  overflow: "hidden",
};

export type AdminTableColumn<T> = {
  id: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  sortable?: {
    label: string;
    direction: SortDirection;
    onAsc: () => void;
    onDesc: () => void;
    ascAriaLabel: string;
    descAriaLabel: string;
    ascTooltipLabel?: string;
    descTooltipLabel?: string;
  };
  /**
   * When true (default), cell content is width-capped and ellipsis-truncated so
   * long unbroken strings cannot expand the column. Full text shows on hover
   * when overflowed.
   * Auto-skipped (unless truncate: true) for id: actions, action, delete, detail,
   * tiers, permissions, roles, taskTypes, recipient. Set false for other wrapping cells.
   */
  truncate?: boolean;
  /** Max width when truncate is enabled. Defaults to ADMIN_TABLE_CELL_MAX_W. */
  maxW?: TableCellProps["maxW"];
  thProps?: TableCellProps;
  tdProps?: TableCellProps;
};

function shouldAutoTruncateColumn(col: { id: string; truncate?: boolean }): boolean {
  if (col.truncate === false) return false;
  if (col.truncate === true) return true;
  // Action / control / multi-badge wrap columns must not be clipped by default
  if (
    /^(actions?|delete|detail|tiers|permissions|roles|taskTypes|recipient)$/i.test(col.id)
  ) {
    return false;
  }
  return true;
}

function getTruncateCellProps(truncate: boolean, maxW?: TableCellProps["maxW"]): TableCellProps {
  if (!truncate) return {};
  return {
    ...DEFAULT_TRUNCATE_CELL_PROPS,
    ...(maxW != null ? { maxW } : {}),
  };
}

/**
 * Root-level truncate wrapper: ellipsis + tooltip only when content overflows.
 * Applied automatically by AdminDataTable — do not wrap cell text in callers.
 */
function TruncatingCellContent({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState("");

  const onMouseEnter = useCallback(() => {
    const el = ref.current;
    if (!el) {
      setTooltip("");
      return;
    }
    const overflowed = el.scrollWidth > el.clientWidth + 1;
    setTooltip(overflowed ? (el.textContent ?? "").trim() : "");
  }, []);

  return (
    <Tooltip label={tooltip} isDisabled={!tooltip} placement="top" hasArrow openDelay={300}>
      <Box
        ref={ref}
        minW={0}
        maxW="100%"
        overflow="hidden"
        textOverflow="ellipsis"
        whiteSpace="nowrap"
        onMouseEnter={onMouseEnter}
        sx={{
          "& > *": {
            minW: 0,
            maxW: "100%",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          },
        }}
      >
        {children}
      </Box>
    </Tooltip>
  );
}

type AdminDataTableFilterContextValue = {
  resetPage: () => void;
  inputBg: string;
};

const AdminDataTableFilterContext = createContext<AdminDataTableFilterContextValue>({
  resetPage: () => {},
  inputBg: "white",
});

function useAdminDataTableFilterContext() {
  return useContext(AdminDataTableFilterContext);
}

/** Search field wired to reset pagination when the value changes. */
export function TableSearchField({
  label = "Search",
  value,
  onChange,
  placeholder,
  helper,
  formControlProps,
  inputGroupProps,
  inputProps,
}: {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  helper?: string;
  formControlProps?: FormControlProps;
  inputGroupProps?: Omit<InputGroupProps, "children">;
  inputProps?: Omit<InputProps, "value" | "onChange" | "placeholder">;
}) {
  const { resetPage, inputBg } = useAdminDataTableFilterContext();
  return (
    <FormControl w={{ base: "full", md: "320px" }} {...formControlProps}>
      <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
        {label}
      </FormLabel>
      <InputGroup size="sm" {...inputGroupProps}>
        <InputLeftElement pointerEvents="none">
          <SearchIcon color="gray.400" />
        </InputLeftElement>
        <Input
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            resetPage();
          }}
          placeholder={placeholder}
          bg={inputBg}
          pl={9}
          {...inputProps}
        />
      </InputGroup>
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
  formControlProps,
  selectProps,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  helper?: string;
  formControlProps?: FormControlProps;
  selectProps?: Omit<SelectProps, "value" | "onChange" | "children">;
}) {
  const { resetPage, inputBg } = useAdminDataTableFilterContext();
  return (
    <FormControl w={{ base: "full", sm: "200px" }} {...formControlProps}>
      <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
        {label}
      </FormLabel>
      <Select
        size="sm"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          resetPage();
        }}
        bg={inputBg}
        {...selectProps}
      >
        {children}
      </Select>
      <FieldHint>{helper}</FieldHint>
    </FormControl>
  );
}

export type AdminDataTableProps<T> = {
  /** Full list (client pagination) or current page rows (server pagination). */
  items: T[];
  columns: AdminTableColumn<T>[];
  getRowKey: (row: T) => string;

  filters?: React.ReactNode;
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
  filterToolbarAlign?: "flex-start" | "center";
  filterToolbarRightContent?: React.ReactNode;
  showFiltersHeading?: boolean;
  filtersHeading?: string;

  /** Client: slice `items`. Server: use controlled page props. None: show all rows. */
  paginate?: "client" | "server" | false;
  initialPageSize?: number;
  pageSizeOptions?: readonly number[];
  /** Required when paginate="server". */
  serverPagination?: UseAdminDataTableServerOptions;

  isLoading?: boolean;
  loadingMessage?: string;
  emptyMessage?: string;
  noResultsMessage?: string;
  /** When set, empty vs filtered-empty messages differ (e.g. total keys before filter). */
  unfilteredCount?: number;

  onRowClick?: (row: T) => void;
  maxHeight?: string;
  tableContainerProps?: Omit<TableContainerProps, "children">;
  size?: "sm" | "md";
  paginationPosition?: "top" | "bottom";
};

function PaginationBlock({
  startRow,
  endRow,
  totalItems,
  page,
  totalPages,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  onFirst,
  onPrev,
  onNext,
  onLast,
  canPrev,
  canNext,
  borderColor,
  bg,
}: {
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
  borderColor: string;
  bg: string;
}) {
  if (totalItems === 0) return null;
  return (
    <TablePaginationBar
      startRow={startRow}
      endRow={endRow}
      totalItems={totalItems}
      page={page}
      totalPages={totalPages}
      pageSize={pageSize}
      pageSizeOptions={pageSizeOptions}
      onPageSizeChange={onPageSizeChange}
      onFirst={onFirst}
      onPrev={onPrev}
      onNext={onNext}
      onLast={onLast}
      canPrev={canPrev}
      canNext={canNext}
      borderColor={borderColor}
      bg={bg}
    />
  );
}

export default function AdminDataTable<T>({
  items,
  columns,
  getRowKey,
  filters,
  hasActiveFilters = false,
  onClearFilters,
  filterToolbarAlign = "flex-start",
  filterToolbarRightContent,
  showFiltersHeading = false,
  filtersHeading = "Filters",
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
}: AdminDataTableProps<T>) {
  const { tableBg, tableHeaderBg, tableRowHoverBg, cardBg, borderColor } = useAdminTableSurface();

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
    }
  );

  const displayItems =
    paginate === "client" ? clientTable.paginatedItems : items;

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

  const handleClearFilters = () => {
    onClearFilters?.();
    pagination?.resetPage();
  };

  const filterContextValue = useMemo(
    () => ({
      resetPage: pagination?.resetPage ?? (() => {}),
      inputBg: cardBg,
    }),
    [pagination?.resetPage, cardBg]
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
    paginate !== false && pagination ? (
      <PaginationBlock
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
        borderColor={borderColor}
        bg={cardBg}
      />
    ) : null;

  return (
    <AdminDataTableFilterContext.Provider value={filterContextValue}>
      <VStack spacing={4} align="stretch" w="100%">
        {filters ? (
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
              {filters}
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
          <>
            {paginationPosition === "top" ? paginationBlock : null}
            <TableContainer maxH={maxHeight} overflowY="auto" {...tableContainerProps}>
              <Table variant="simple" bg={tableBg} size={size} w="100%">
                <Thead bg={tableHeaderBg}>
                  <Tr>
                    {columns.map((col) => {
                      const truncate = shouldAutoTruncateColumn(col);
                      return (
                        <Th
                          key={col.id}
                          {...getTruncateCellProps(truncate, col.maxW)}
                          {...col.thProps}
                        >
                          {col.sortable ? (
                            <TableSortHeader
                              label={col.sortable.label}
                              direction={col.sortable.direction}
                              onAsc={col.sortable.onAsc}
                              onDesc={col.sortable.onDesc}
                              ascAriaLabel={col.sortable.ascAriaLabel}
                              descAriaLabel={col.sortable.descAriaLabel}
                              ascTooltipLabel={col.sortable.ascTooltipLabel}
                              descTooltipLabel={col.sortable.descTooltipLabel}
                            />
                          ) : (
                            col.header
                          )}
                        </Th>
                      );
                    })}
                  </Tr>
                </Thead>
                <Tbody>
                  {displayItems.map((row) => (
                    <Tr
                      key={getRowKey(row)}
                      onClick={onRowClick ? () => onRowClick(row) : undefined}
                      cursor={onRowClick ? "pointer" : undefined}
                      _hover={{ bg: tableRowHoverBg }}
                      transition="background 0.15s"
                    >
                      {columns.map((col) => {
                        const truncate = shouldAutoTruncateColumn(col);
                        const content = col.cell(row);
                        return (
                          <Td
                            key={col.id}
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
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </TableContainer>
            {paginationPosition === "bottom" ? paginationBlock : null}
          </>
        )}
      </VStack>
    </AdminDataTableFilterContext.Provider>
  );
}
