// Service Registry tab: filterable/searchable table of all registered services
import React from "react";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
  type DataTableSortState,
} from "../common/table";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type { Service } from "../../services/servicesManagementService";
import {
  serviceListCellKey,
  type ServiceListColumnDef,
} from "./serviceListColumns";
import {
  buildClientServiceFilterDefs,
  buildServerServiceFilterDefs,
  buildServiceRegistrySearch,
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
  onSearchQueryChange: (value: string) => void;
  filterStatus: string;
  onFilterStatusChange: (value: string) => void;
  filterTaskType: string;
  onFilterTaskTypeChange: (value: string) => void;
  taskTypeNames: string[];
  filterTier: string;
  onFilterTierChange: (value: string) => void;
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
  const nameColumn = options.serverColumns?.find(
    (column) => column.filterable && serviceListCellKey(column.id) === "name",
  );
  return buildServerServiceFilterDefs({
    columns: options.serverColumns ?? [],
    nameColumnId: nameColumn?.id,
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
  onSearchQueryChange,
  filterStatus,
  onFilterStatusChange,
  filterTaskType,
  onFilterTaskTypeChange,
  taskTypeNames,
  filterTier,
  onFilterTierChange,
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
  const nameColumn = serverColumns?.find(
    (column) => column.filterable && serviceListCellKey(column.id) === "name",
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
    filterTier,
    onFilterTierChange,
    tierFilterOptions,
  });
  const search = buildServiceRegistrySearch({
    serverMode,
    nameColumn,
    serverFilterValues,
    onServerFilterChange,
    searchQuery,
    onSearchQueryChange,
  });
  const serverPagination = resolveServerPagination({
    serverMode,
    serverPage,
    serverPageSize,
    serverTotal,
    onServerPageChange,
    onServerPageSizeChange,
  });

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
      search={search}
      filterDefs={serverMode ? serverFilterDefs : clientFilterDefs}
    />
  );
};

export default ServiceRegistryTab;
