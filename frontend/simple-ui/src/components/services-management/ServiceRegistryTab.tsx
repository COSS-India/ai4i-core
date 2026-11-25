// Service Registry tab: filterable/searchable table of all registered services
import React from "react";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
  type DataTableSortState,
} from "../common/table";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type { Service } from "../../services/servicesManagementService";
import type { ServiceListColumnDef } from "./serviceListColumns";
import { buildServerServiceFilterDefs } from "./serviceRegistryFilters";

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
  taskTypeNames: string[];
  tierFilterOptions: ServiceTierFilterOption[];
  hasActiveFilters: boolean;
  onClearFilters: () => void;
  /** Column picker, rendered at the end of the filter toolbar. */
  columnPicker?: React.ReactNode;
  /** Filters and paging run on GET /services, using these columns' filter metadata. */
  serverColumns: readonly ServiceListColumnDef[];
  serverFilterValues: Record<string, string>;
  onServerFilterChange: (columnId: string, value: string) => void;
  serverPage: number;
  serverPageSize: number;
  serverTotal: number;
  onServerPageChange: (page: number) => void;
  onServerPageSizeChange: (size: number) => void;
}

function serviceRegistryRowKey(service: Service): string {
  return service.serviceId || service.service_id || "";
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
  taskTypeNames,
  tierFilterOptions,
  hasActiveFilters,
  onClearFilters,
  columnPicker,
  serverColumns,
  serverFilterValues,
  onServerFilterChange,
  serverPage,
  serverPageSize,
  serverTotal,
  onServerPageChange,
  onServerPageSizeChange,
}) => {
  const filterDefs = buildServerServiceFilterDefs({
    columns: serverColumns,
    serverFilterValues,
    taskTypeNames,
    tierFilterOptions,
    onChange: onServerFilterChange,
  });
  const serverPagination = {
    page: serverPage,
    pageSize: serverPageSize,
    totalItems: serverTotal,
    onPageChange: onServerPageChange,
    onPageSizeChange: onServerPageSizeChange,
  };

  return (
    <DataTable
      layout="admin"
      fillHeight
      key={tableKey}
      items={items}
      columns={columns}
      sort={sort}
      onSortChange={onSortChange}
      getRowKey={serviceRegistryRowKey}
      onRowClick={onRowClick}
      showRowChevron
      paginate="server"
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
      filterDefs={filterDefs}
      autoColumnSort
    />
  );
};

export default ServiceRegistryTab;
