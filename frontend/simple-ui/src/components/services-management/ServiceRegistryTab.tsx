// Service Registry tab: filterable/searchable table of all registered services
import React from "react";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
  type DataTableSortState,
} from "../common/table";
import { SERVICE_TIER, formatModelTaskTypeLabel } from "../../config/constants";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type { Service } from "../../services/servicesManagementService";

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
}) => {
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
      paginate="client"
      paginationPosition="bottom"
      pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
      isLoading={isLoading}
      loadingMessage="Loading services..."
      emptyMessage="No services in the registry yet."
      noResultsMessage="No results found. Try adjusting your search or filters."
      unfilteredCount={totalServicesCount}
      hasActiveFilters={hasActiveFilters}
      onClearFilters={onClearFilters}
      search={{
        label: "Search",
        value: searchQuery,
        onChange: onSearchQueryChange,
        placeholder: "Search by service name...",
        fields: ["service_name", "name"],
      }}
      filterDefs={[
        {
          id: "status",
          label: "Status",
          type: "select",
          param: "status",
          value: filterStatus,
          onChange: onFilterStatusChange,
          width: { base: "full", sm: "140px" },
          options: [
            { label: "All", value: "" },
            { label: "Published", value: "published" },
            { label: "Unpublished", value: "unpublished" },
          ],
        },
        {
          id: "taskType",
          label: "Model Task Type",
          type: "select",
          param: "model_task_type",
          value: filterTaskType,
          onChange: onFilterTaskTypeChange,
          width: { base: "full", sm: "160px" },
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
          width: { base: "full", sm: "180px" },
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
