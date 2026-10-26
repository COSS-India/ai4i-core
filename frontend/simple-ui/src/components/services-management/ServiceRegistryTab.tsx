// Service Registry tab: filterable/searchable table of all registered services
import React from "react";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
  type DataTableFilterDef,
  type DataTableSortState,
} from "../common/table";
import { SERVICE_TIER, formatModelTaskTypeLabel } from "../../config/constants";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type { Service } from "../../services/servicesManagementService";
import {
  serviceListCellKey,
  type ServiceListColumnDef,
} from "./serviceListColumns";

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

const ServiceRegistryTab: React.FC<ServiceRegistryTabProps> = ({
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
  const serverMode = Boolean(serverColumns && onServerFilterChange && onServerPageChange);
  const nameColumn = serverColumns?.find(
    (column) => column.filterable && serviceListCellKey(column.id) === "name",
  );
  const serverFilterDefs: DataTableFilterDef[] = serverMode
    ? (serverColumns ?? []).flatMap((column): DataTableFilterDef[] => {
        if (!column.filterable || !column.filter || column.id === nameColumn?.id) return [];
        const value = serverFilterValues?.[column.id] ?? "";
        const kind = column.filter.type;
        if (kind === "single_select" || kind === "multi_select") {
          const apiOptions = column.filter.options ?? [];
          const taskOptions =
            serviceListCellKey(column.id) === "task"
              ? taskTypeNames
                  .filter((name) =>
                    apiOptions.length === 0 ||
                    apiOptions.some((option) => option.value.toLowerCase() === name.toLowerCase()),
                  )
                  .map((name) => ({ label: formatModelTaskTypeLabel(name), value: name }))
              : serviceListCellKey(column.id) === "tier" && apiOptions.length === 0
                ? tierFilterOptions.map((tier) => ({ label: tier.name, value: tier.id }))
                : apiOptions;
          const showAll =
            serviceListCellKey(column.id) !== "task" || taskTypeNames.length > 1;
          return [{
            id: column.id,
            label: column.label,
            type: "select" as const,
            param: column.filter.params[0],
            value:
              serviceListCellKey(column.id) === "task" && taskTypeNames.length === 1
                ? taskTypeNames[0]
                : value,
            onChange: (next: string) => onServerFilterChange?.(column.id, next),
            options: [
              ...(showAll ? [{ label: "All", value: "" }] : []),
              ...taskOptions,
            ],
          }];
        }
        if (kind === "date" || kind === "datetime" || kind === "datetime-local") {
          return [{
            id: column.id,
            label: column.label,
            type: "date" as const,
            param: column.filter.params[0],
            inputType: kind === "date" ? "date" as const : "datetime-local" as const,
            value,
            onChange: (next: string) => onServerFilterChange?.(column.id, next),
          }];
        }
        if (kind !== "text") return [];
        return [{
          id: column.id,
          label: column.label,
          type: "text" as const,
          param: column.filter.params[0],
          value,
          onChange: (next: string) => onServerFilterChange?.(column.id, next),
        }];
      })
    : [];

  return (
    <DataTable
      layout="admin"
      key={tableKey}
      items={items}
      columns={columns}
      sort={sort}
      onSortChange={onSortChange}
      getRowKey={(service) => service.serviceId || service.service_id || ""}
      onRowClick={onRowClick}
      paginate={serverMode ? "server" : "client"}
      paginationPosition="bottom"
      pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
      serverPagination={
        serverMode && onServerPageChange && onServerPageSizeChange
          ? {
              page: serverPage,
              pageSize: serverPageSize,
              totalItems: serverTotal,
              onPageChange: onServerPageChange,
              onPageSizeChange: onServerPageSizeChange,
            }
          : undefined
      }
      isLoading={isLoading}
      loadingMessage="Loading services..."
      emptyMessage="No services in the registry yet."
      noResultsMessage="No results found. Try adjusting your search or filters."
      unfilteredCount={totalServicesCount}
      hasActiveFilters={hasActiveFilters}
      onClearFilters={onClearFilters}
      filterToolbarRightContent={columnPicker}
      search={
        serverMode
          ? nameColumn
            ? {
                label: nameColumn.label,
                value: serverFilterValues?.[nameColumn.id] ?? "",
                onChange: (value) => onServerFilterChange?.(nameColumn.id, value),
                placeholder: "Search by service name...",
                debounceMs: 400,
                fields: ["name"],
              }
            : undefined
          : {
              label: "Search",
              value: searchQuery,
              onChange: onSearchQueryChange,
              placeholder: "Search by service name...",
              fields: ["service_name", "name"],
            }
      }
      filterDefs={serverMode ? serverFilterDefs : [
        {
          id: "status",
          label: "Status",
          type: "select",
          param: "status",
          value: filterStatus,
          onChange: onFilterStatusChange,
          options: [
            { label: "All", value: "" },
            { label: "Published", value: "published" },
            { label: "Unpublished", value: "unpublished" },
          ],
        },
        {
          id: "taskType",
          label: "Task Type",
          type: "select",
          param: "model_task_type",
          value: filterTaskType,
          onChange: onFilterTaskTypeChange,
          options: [
            ...(taskTypeNames.length > 1 ? [{ label: "All", value: "" }] : []),
            ...taskTypeNames.map((t) => ({
              label: formatModelTaskTypeLabel(t),
              value: t,
            })),
          ],
        },
        {
          id: "tier",
          label: "Tier",
          // No `param`: GET /services has no tier filter, so this one is
          // applied client-side rather than refetching.
          type: "select",
          value: filterTier,
          onChange: onFilterTierChange,
          options: [
            { label: "All", value: SERVICE_TIER.FILTER.ALL },
            ...tierFilterOptions.map((tier) => ({
              label: tier.name,
              value: tier.id,
            })),
            { label: "No tier", value: SERVICE_TIER.FILTER.NONE },
          ],
        },
      ]}
    />
  );
};

export default ServiceRegistryTab;
