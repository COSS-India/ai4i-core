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
} from "../common/AdminDataTable";
import {
  MODEL_TASK_TYPE_LIST,
  MODEL_VERSION,
  MODEL_VERSION_FILTER_LIST,
  formatModelTaskTypeLabel,
  formatModelVersionFilterLabel,
} from "../../config/constants";
import type { UseModelManagementReturn } from "../../hooks/useModelManagement";

export function ModelsTable(props: UseModelManagementReturn) {
  const {
    cardBg,
    cardBorder,
    filterTaskType,
    filterVersionStatus,
    registryTableItems,
    modelColumns,
    isLoading,
    models,
    hasActiveFilters,
    clearAllFilters,
    searchQuery,
    setSearchQuery,
    setFilterVersionStatus,
    setFilterTaskType,
    handleViewModel,
  } = props;

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <Heading size="md" color="gray.700" userSelect="none" cursor="default">
          Model Registry
        </Heading>
      </CardHeader>
      <CardBody>
        <AdminDataTable
          key={`${filterTaskType}-${filterVersionStatus}`}
          items={registryTableItems}
          columns={modelColumns}
          getRowKey={(model) => model.modelId}
          onRowClick={(model) => handleViewModel(model.modelId)}
          paginate="client"
          pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
          isLoading={isLoading}
          loadingMessage="Loading models..."
          emptyMessage="No models in the registry yet."
          noResultsMessage="No results found. Try adjusting your search or filters."
          unfilteredCount={models.length}
          hasActiveFilters={hasActiveFilters}
          onClearFilters={clearAllFilters}
          filters={
            <VStack align="stretch" spacing={3} w="full">
              <HStack flexWrap="wrap" spacing={3} align="flex-end">
                <TableSearchField
                  label="Search"
                  value={searchQuery}
                  onChange={setSearchQuery}
                  placeholder="Search by model name..."
                  formControlProps={{ w: { base: "full", md: "280px" } }}
                />
                <TableSelectField
                  label="Status"
                  value={filterVersionStatus}
                  onChange={setFilterVersionStatus}
                  formControlProps={{ w: { base: "full", sm: "140px" } }}
                >
                  <option value={MODEL_VERSION.FILTER.ALL}>All</option>
                  {MODEL_VERSION_FILTER_LIST.map((s) => (
                    <option key={s} value={s}>
                      {formatModelVersionFilterLabel(s)}
                    </option>
                  ))}
                </TableSelectField>
                <TableSelectField
                  label="Task type"
                  value={filterTaskType}
                  onChange={setFilterTaskType}
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
              {hasActiveFilters && (
                <HStack spacing={2} flexWrap="wrap">
                  {searchQuery.trim() && (
                    <Badge
                      colorScheme="blue"
                      fontSize="xs"
                      px={2}
                      py={1}
                      cursor="pointer"
                      onClick={() => setSearchQuery("")}
                      _hover={{ opacity: 0.8 }}
                    >
                      Search: &quot;{searchQuery.trim()}&quot; ×
                    </Badge>
                  )}
                  {filterVersionStatus && (
                    <Badge
                      colorScheme="gray"
                      fontSize="xs"
                      px={2}
                      py={1}
                      cursor="pointer"
                      onClick={() => setFilterVersionStatus("")}
                      _hover={{ opacity: 0.8 }}
                    >
                      Status: {formatModelVersionFilterLabel(filterVersionStatus)} ×
                    </Badge>
                  )}
                  {filterTaskType && (
                    <Badge
                      colorScheme="gray"
                      fontSize="xs"
                      px={2}
                      py={1}
                      cursor="pointer"
                      onClick={() => setFilterTaskType("")}
                      _hover={{ opacity: 0.8 }}
                    >
                      Task: {formatModelTaskTypeLabel(filterTaskType)} ×
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
