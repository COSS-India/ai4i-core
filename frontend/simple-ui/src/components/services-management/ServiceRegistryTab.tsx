// Service Registry tab: filterable/searchable table of all registered services
import React, { useCallback, useMemo } from "react";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
  type DataTableColumnFilters,
  type DataTableSortState,
} from "../common/table";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type { Service } from "../../services/servicesManagementService";
import {
  serviceListCellKey,
  type ServiceListColumnDef,
} from "./serviceListColumns";
import {
  applyDateRangeColumnFilter,
  buildClientServiceFilterDefs,
  buildServerServiceFilterDefs,
  dateRangeColumnFilterValue,
  SERVICE_COLUMN_DATE_KEYS,
  SERVICE_COLUMN_SEARCH_KEYS,
} from "./serviceRegistryFilters";

interface ServiceRegistryTabProps {
  items: Service[];
  columns: DataTableColumn<Service>[];
  sort?: DataTableSortState;
  onSortChange?: (next: DataTableSortState) => void;
  isLoading: boolean;
  totalServicesCount: number;
  onRowClick: (service: Service) => void;
  tableKey: string;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  filterStatus: string;
  onFilterStatusChange: (value: string) => void;
  filterTaskType: string;
  onFilterTaskTypeChange: (value: string) => void;
  taskTypeNames: string[];
  tierFilterOptions: ServiceTierFilterOption[];
  hasActiveFilters: boolean;
  onClearFilters: () => void;
  /** Column picker, rendered at the end of the filter toolbar. */
  columnPicker?: React.ReactNode;
  /** When set, filters and paging come from GET /services/columns and GET /services. */
  serverColumns?: readonly ServiceListColumnDef[];
  serverFilterValues?: Record<string, string>;
  onServerFilterChange?: (columnId: string, value: string) => void;
  serverPage?: number;
  serverPageSize?: number;
  serverTotal?: number;
  onServerPageChange?: (page: number) => void;
  onServerPageSizeChange?: (size: number) => void;
}

function serviceRegistryRowKey(service: Service): string {
  return service.serviceId || service.service_id || "";
}

function resolveServerFilterDefs(options: {
  serverMode: boolean;
  serverColumns?: readonly ServiceListColumnDef[];
  serverFilterValues?: Record<string, string>;
  taskTypeNames: string[];
  tierFilterOptions: ServiceTierFilterOption[];
  onServerFilterChange?: (columnId: string, value: string) => void;
}) {
  if (!options.serverMode || !options.onServerFilterChange) return [];
  return buildServerServiceFilterDefs({
    columns: options.serverColumns ?? [],
    serverFilterValues: options.serverFilterValues,
    taskTypeNames: options.taskTypeNames,
    tierFilterOptions: options.tierFilterOptions,
    onChange: options.onServerFilterChange,
  });
}

function resolveServerPagination(options: {
  serverMode: boolean;
  serverPage: number;
  serverPageSize: number;
  serverTotal: number;
  onServerPageChange?: (page: number) => void;
  onServerPageSizeChange?: (size: number) => void;
}) {
  if (
    !options.serverMode ||
    !options.onServerPageChange ||
    !options.onServerPageSizeChange
  ) {
    return undefined;
  }
  return {
    page: options.serverPage,
    pageSize: options.serverPageSize,
    totalItems: options.serverTotal,
    onPageChange: options.onServerPageChange,
    onPageSizeChange: options.onServerPageSizeChange,
  };
}

const ServiceRegistryTab: React.FC<Readonly<ServiceRegistryTabProps>> = ({
  items,
  columns,
  sort,
  onSortChange,
  isLoading,
  totalServicesCount,
  onRowClick,
  tableKey,
  searchQuery,
  onSearchChange,
  filterStatus,
  onFilterStatusChange,
  filterTaskType,
  onFilterTaskTypeChange,
  taskTypeNames,
  tierFilterOptions,
  hasActiveFilters,
  onClearFilters,
  columnPicker,
  serverColumns,
  serverFilterValues,
  onServerFilterChange,
  serverPage = 1,
  serverPageSize = 25,
  serverTotal = 0,
  onServerPageChange,
  onServerPageSizeChange,
}) => {
  const serverMode = Boolean(
    serverColumns && onServerFilterChange && onServerPageChange,
  );
  const serverFilterDefs = resolveServerFilterDefs({
    serverMode,
    serverColumns,
    serverFilterValues,
    taskTypeNames,
    tierFilterOptions,
    onServerFilterChange,
  });
  const clientFilterDefs = buildClientServiceFilterDefs({
    filterStatus,
    onFilterStatusChange,
    filterTaskType,
    onFilterTaskTypeChange,
    taskTypeNames,
  });
  const serverPagination = resolveServerPagination({
    serverMode,
    serverPage,
    serverPageSize,
    serverTotal,
    onServerPageChange,
    onServerPageSizeChange,
  });

  const columnFilters = useMemo((): DataTableColumnFilters | undefined => {
    if (!serverMode || !serverColumns) return undefined;
    const next: DataTableColumnFilters = {};
    for (const column of serverColumns) {
      const cellKey = serviceListCellKey(column.id);
      if (SERVICE_COLUMN_DATE_KEYS.has(cellKey)) {
        const value = dateRangeColumnFilterValue(column.id, serverFilterValues);
        if (value) next[column.id] = value;
        continue;
      }
      if (!SERVICE_COLUMN_SEARCH_KEYS.has(cellKey)) continue;
      const value = serverFilterValues?.[column.id];
      if (value) next[column.id] = value;
    }
    return next;
  }, [serverMode, serverColumns, serverFilterValues]);

  const handleColumnFiltersChange = useCallback(
    (next: DataTableColumnFilters) => {
      if (serverMode && serverColumns && onServerFilterChange) {
        for (const column of serverColumns) {
          const cellKey = serviceListCellKey(column.id);
          if (SERVICE_COLUMN_DATE_KEYS.has(cellKey)) {
            applyDateRangeColumnFilter(
              column.id,
              next[column.id] ?? "",
              onServerFilterChange,
            );
            continue;
          }
          if (SERVICE_COLUMN_SEARCH_KEYS.has(cellKey)) {
            onServerFilterChange(column.id, next[column.id] ?? "");
          }
        }
      }
    },
    [serverMode, serverColumns, onServerFilterChange],
  );

  return (
    <DataTable
      layout="admin"
      key={tableKey}
      items={items}
      columns={columns}
      sort={sort}
      onSortChange={onSortChange}
      getRowKey={serviceRegistryRowKey}
      onRowClick={onRowClick}
      showRowChevron
      paginate={serverMode ? "server" : "client"}
      paginationPosition="bottom"
      pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
      serverPagination={serverPagination}
      isLoading={isLoading}
      loadingMessage="Loading services..."
      emptyMessage="No services in the registry yet."
      noResultsMessage="No results found. Try adjusting your search or filters."
      unfilteredCount={totalServicesCount}
      hasActiveFilters={hasActiveFilters}
      onClearFilters={onClearFilters}
      filterToolbarRightContent={columnPicker}
      search={{
        label: "Search",
        value: searchQuery,
        onChange: onSearchChange,
        placeholder: "Search by name",
        debounceMs: 400,
        width: { base: "full", sm: "220px" },
      }}
      filterDefs={serverMode ? serverFilterDefs : clientFilterDefs}
      columnSearch
      autoColumnSort
      columnFilters={columnFilters}
      onColumnFiltersChange={serverMode ? handleColumnFiltersChange : undefined}
    />
  );
};

export default ServiceRegistryTab;
