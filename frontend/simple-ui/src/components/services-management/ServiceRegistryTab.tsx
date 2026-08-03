// Service Registry tab: filterable/searchable table of all registered services
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import { formatModelTaskTypeLabel } from "../../config/constants";
import type { Service } from "../../services/servicesManagementService";

interface ServiceRegistryTabProps {
  cardBg: string;
  cardBorder: string;
  items: Service[];
  columns: AdminTableColumn<Service>[];
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
        <AdminDataTable
          key={tableKey}
          items={items}
          columns={columns}
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
          filters={
            <VStack align="stretch" spacing={3} w="full">
              <HStack flexWrap="wrap" spacing={3} align="flex-end">
                <TableSearchField
                  label="Search"
                  value={searchQuery}
                  onChange={onSearchQueryChange}
                  placeholder="Search by service name..."
                  formControlProps={{ w: { base: "full", md: "280px" } }}
                />
                <TableSelectField
                  label="Status"
                  value={filterStatus}
                  onChange={onFilterStatusChange}
                  formControlProps={{ w: { base: "full", sm: "140px" } }}
                >
                  <option value="">All</option>
                  <option value="published">Published</option>
                  <option value="unpublished">Unpublished</option>
                </TableSelectField>
                <TableSelectField
                  label="Model Task Type"
                  value={filterTaskType}
                  onChange={onFilterTaskTypeChange}
                  formControlProps={{ w: { base: "full", sm: "160px" } }}
                >
                  {taskTypeNames?.map((t) => (
                    <option key={t} value={t}>
                      {formatModelTaskTypeLabel(t)}
                    </option>
                  ))}
                </TableSelectField>
              </HStack>
              {hasActiveFilters && (
                <HStack spacing={2} flexWrap="wrap">
                  {searchQuery.trim() && (
                    <Badge
                      colorScheme="blue"
                      fontSize="xs"
                      px={2}
                      py={1}
                      cursor="pointer"
                      onClick={() => onSearchQueryChange("")}
                      _hover={{ opacity: 0.8 }}
                    >
                      Search: &quot;{searchQuery.trim()}&quot; ×
                    </Badge>
                  )}
                  {filterStatus && (
                    <Badge
                      colorScheme="gray"
                      fontSize="xs"
                      px={2}
                      py={1}
                      cursor="pointer"
                      onClick={() => onFilterStatusChange("")}
                      _hover={{ opacity: 0.8 }}
                    >
                      Status:{" "}
                      {filterStatus === "published"
                        ? "Published"
                        : "Unpublished"}{" "}
                      ×
                    </Badge>
                  )}
                </HStack>
              )}
            </VStack>
          }
        />
      </CardBody>
    </Card>
  );
};

export default ServiceRegistryTab;
