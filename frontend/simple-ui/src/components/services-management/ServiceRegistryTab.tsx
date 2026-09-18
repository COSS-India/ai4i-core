// Service Registry tab: filterable/searchable table of all registered services
import {
  Card,
  CardBody,
  CardHeader,
  Heading,
} from "@chakra-ui/react";
import React from "react";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
  type DataTableSortState,
} from "../common/table";
import { formatModelTaskTypeLabel } from "../../config/constants";
import type { Service } from "../../services/servicesManagementService";

interface ServiceRegistryTabProps {
  cardBg: string;
  cardBorder: string;
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
  hasActiveFilters: boolean;
  onClearFilters: () => void;
}

const ServiceRegistryTab: React.FC<ServiceRegistryTabProps> = ({
  cardBg,
  cardBorder,
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
  hasActiveFilters,
  onClearFilters,
}) => {
  return (
    <Card
      bg={cardBg}
      borderColor={cardBorder}
      borderWidth="1px"
      boxShadow="none"
    >
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          Service Registry
        </Heading>
      </CardHeader>
      <CardBody>
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
          ]}
        />
      </CardBody>
    </Card>
  );
};

export default ServiceRegistryTab;
