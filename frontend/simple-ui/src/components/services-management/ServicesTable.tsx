import React from "react";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  VStack,
} from "@chakra-ui/react";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  TableSelectField,
} from "../common/AdminDataTable";
import { MODEL_TASK_TYPE_LIST, formatModelTaskTypeLabel } from "../../config/constants";
import type { UseServicesManagementReturn } from "../../hooks/useServicesManagement";

export type ServicesTableProps = UseServicesManagementReturn;

export default function ServicesTable(sm: ServicesTableProps) {
  return (
    <Card bg={sm.cardBg} borderColor={sm.cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          Service Registry
        </Heading>
      </CardHeader>
      <CardBody>
        <AdminDataTable
          key={`${sm.filterStatus}-${sm.filterTaskType}-${sm.registryEpoch}`}
          items={sm.registryTableItems}
          columns={sm.serviceColumns}
          getRowKey={(service) =>
            service.serviceId || service.service_id || ""
          }
          onRowClick={(service) =>
            sm.handleViewService(service.serviceId || service.service_id || "")
          }
          paginate="client"
          pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
          isLoading={sm.isLoading}
          loadingMessage="Loading services..."
          emptyMessage="No services in the registry yet."
          noResultsMessage="No results found. Try adjusting your search or filters."
          unfilteredCount={sm.services.length}
          hasActiveFilters={sm.hasActiveFilters}
          onClearFilters={sm.clearAllFilters}
          filters={
            <VStack align="stretch" spacing={3} w="full">
              <HStack flexWrap="wrap" spacing={3} align="flex-end">
                <TableSearchField
                  label="Search"
                  value={sm.searchQuery}
                  onChange={sm.setSearchQuery}
                  placeholder="Search by service name..."
                  formControlProps={{ w: { base: "full", md: "280px" } }}
                />
                <TableSelectField
                  label="Status"
                  value={sm.filterStatus}
                  onChange={sm.setFilterStatus}
                  formControlProps={{ w: { base: "full", sm: "140px" } }}
                >
                  <option value="">All</option>
                  <option value="published">Published</option>
                  <option value="unpublished">Unpublished</option>
                </TableSelectField>
                <TableSelectField
                  label="Model Task Type"
                  value={sm.filterTaskType}
                  onChange={sm.setFilterTaskType}
                  formControlProps={{ w: { base: "full", sm: "160px" } }}
                >
                  <option value="">All</option>
                  {MODEL_TASK_TYPE_LIST.map((t) => (
                    <option key={t} value={t}>
                      {formatModelTaskTypeLabel(t)}
                    </option>
                  ))}
                </TableSelectField>
              </HStack>
              {sm.hasActiveFilters && (
                <HStack spacing={2} flexWrap="wrap">
                  {sm.searchQuery.trim() && (
                    <Badge
                      colorScheme="blue"
                      fontSize="xs"
                      px={2}
                      py={1}
                      cursor="pointer"
                      onClick={() => sm.setSearchQuery("")}
                      _hover={{ opacity: 0.8 }}
                    >
                      Search: &quot;{sm.searchQuery.trim()}&quot; ×
                    </Badge>
                  )}
                  {sm.filterStatus && (
                    <Badge
                      colorScheme="gray"
                      fontSize="xs"
                      px={2}
                      py={1}
                      cursor="pointer"
                      onClick={() => sm.setFilterStatus("")}
                      _hover={{ opacity: 0.8 }}
                    >
                      Status:{" "}
                      {sm.filterStatus === "published" ? "Published" : "Unpublished"}{" "}
                      ×
                    </Badge>
                  )}
                  {sm.filterTaskType && (
                    <Badge
                      colorScheme="gray"
                      fontSize="xs"
                      px={2}
                      py={1}
                      cursor="pointer"
                      onClick={() => sm.setFilterTaskType("")}
                      _hover={{ opacity: 0.8 }}
                    >
                      Model Task Type: {formatModelTaskTypeLabel(sm.filterTaskType)} ×
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
}
