// Services Management: wires useServicesManagement's state/handlers to the
// Service Registry / Create-Edit Service / View Service tabs.
import {
  Badge,
  Box,
  Card,
  Grid,
  HStack,
  IconButton,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import { FaDownload, FaUpload } from "react-icons/fa";
import React, { useMemo } from "react";
import ManagementPageHeader from "../common/ManagementPageHeader";
import type { Service } from "../../services/servicesManagementService";
import ConfirmDialog from "../common/ConfirmDialog";
import { useAdminTableSurface } from "../common/TableControls";
import { type AdminTableColumn } from "../common/AdminDataTable";
import { useServicesManagement } from "../../hooks/useServicesManagement";
import ServiceRegistryTab from "./ServiceRegistryTab";
import ServiceFormTab from "./ServiceFormTab";
import ServiceDetailTab from "./ServiceDetailTab";

function getTaskColor(taskType?: string) {
  if (!taskType) return "gray";
  switch (taskType.toLowerCase()) {
    case "asr":
      return "orange";
    case "nmt":
      return "green";
    case "tts":
      return "blue";
    case "llm":
      return "purple";
    default:
      return "gray";
  }
}

function isServiceModelDeprecated(
  service: Service | null | undefined,
): boolean {
  if (!service) return false;
  const modelVersionStatus =
    (service.model as any)?.versionStatus ??
    (service.model as any)?.version_status ??
    (service as any).versionStatus ??
    (service as any).version_status;
  return (
    typeof modelVersionStatus === "string" &&
    modelVersionStatus.toLowerCase() === "deprecated"
  );
}

const ServicesManagement: React.FC = () => {
  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();
  const {
    isRegistryReadOnly,
    activeTab,
    handleTabChange,
    registryTableItems,
    totalServicesCount,
    isLoading,
    tableKey,
    searchQuery,
    setSearchQuery,
    filterStatus,
    setFilterStatus,
    filterTaskType,
    setFilterTaskType,
    taskTypeNames,
    hasActiveFilters,
    clearAllFilters,
    nameSortDirection,
    handleSortNameAsc,
    handleSortNameDesc,
    handleViewService,
    handleEditService,
    handleDeleteClick,
    deletingServiceUuid,
    editingService,
    formData,
    handleInputChange,
    handleTaskTypeChange,
    handleModelNameChange,
    isLoadingModels,
    filteredModelsForDropdown,
    unitType,
    pricePerUnit,
    setPricePerUnit,
    unitSize,
    setUnitSize,
    selectedTiers,
    toggleTier,
    availableTiers,
    isCreateFormModelSelected,
    canCreateService,
    isSubmitting,
    handleSubmit,
    handleCancelForm,
    selectedService,
    isViewingService,
    selectedServiceModelDeprecated,
    viewServiceUnitType,
    unpublishingServiceUuid,
    publishingServiceUuid,
    requestPublish,
    requestUnpublish,
    isOpen,
    onClose,
    handleDeleteConfirm,
    serviceToDelete,
    cancelRef,
    isPublishConfirmOpen,
    closePublishConfirm,
    handlePublishConfirm,
    confirmPublishService,
    cancelPublishRef,
    isUnpublishConfirmOpen,
    closeUnpublishConfirm,
    handleUnpublishConfirm,
    confirmUnpublishService,
    cancelUnpublishRef,
  } = useServicesManagement();

  const serviceColumns = useMemo((): AdminTableColumn<Service>[] => {
    return [
      {
        id: "name",
        header: "Name",
        sortable: {
          label: "Name",
          direction: nameSortDirection,
          onAsc: handleSortNameAsc,
          onDesc: handleSortNameDesc,
          ascAriaLabel: "Sort services by name ascending",
          descAriaLabel: "Sort services by name descending",
        },
        cell: (service) => (
          <Text fontSize="sm" noOfLines={1} title={service.name}>
            {service.name || "N/A"}
          </Text>
        ),
      },
      {
        id: "task",
        header: "Model Task Type",
        cell: (service) => (
          <Badge
            colorScheme={getTaskColor(
              service.model?.task?.type ||
                service.task?.type ||
                service.task_type,
            )}
            fontSize="sm"
            p={1}
          >
            {(
              service.model?.task?.type ||
              service.task?.type ||
              service.task_type
            )?.toUpperCase() || "N/A"}
          </Badge>
        ),
      },
      {
        id: "tiers",
        header: "Tiers",
        cell: (service) => {
          const names = service.tierNames;
          if (!names || names.length === 0) {
            return (
              <Text fontSize="sm" color="gray.400">
                —
              </Text>
            );
          }
          return (
            <HStack spacing={1} flexWrap="wrap">
              {names.map((name) => (
                <Badge
                  key={name}
                  colorScheme="gray"
                  fontSize="xs"
                  px={2}
                  py={0.5}
                >
                  {name}
                </Badge>
              ))}
            </HStack>
          );
        },
      },
      {
        id: "status",
        header: "Status",
        cell: (service) => (
          <Badge
            colorScheme={service.isPublished === true ? "green" : "gray"}
            fontSize="sm"
            p={1}
          >
            {service.isPublished === true ? "Published" : "Unpublished"}
          </Badge>
        ),
      },
      {
        id: "created",
        header: "Created At",
        cell: (service) => (
          <Text fontSize="sm" color="gray.600">
            {service.createdAt
              ? new Date(service.createdAt).toLocaleDateString()
              : "N/A"}
          </Text>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (service) => (
          <HStack spacing={1}>
            <Tooltip label="View" placement="top" hasArrow>
              <IconButton
                aria-label="View"
                icon={<ViewIcon />}
                size="sm"
                variant="ghost"
                colorScheme="blue"
                _hover={{ bg: "blue.50" }}
                onClick={() =>
                  handleViewService(
                    service.serviceId || service.service_id || "",
                  )
                }
              />
            </Tooltip>
            {!isRegistryReadOnly && (
              <Tooltip label="Edit" placement="top" hasArrow>
                <IconButton
                  aria-label="Edit"
                  icon={<EditIcon />}
                  size="sm"
                  variant="ghost"
                  colorScheme="blue"
                  _hover={{ bg: "blue.50" }}
                  onClick={() =>
                    handleEditService(
                      service.serviceId || service.service_id || "",
                    )
                  }
                />
              </Tooltip>
            )}
            {!isRegistryReadOnly &&
              (service.isPublished === true ? (
                <Tooltip label="Unpublish" placement="top" hasArrow>
                  <IconButton
                    aria-label="Unpublish"
                    icon={<FaDownload />}
                    size="sm"
                    variant="ghost"
                    colorScheme="red"
                    _hover={{ bg: "red.50" }}
                    onClick={() => requestUnpublish(service)}
                    isLoading={unpublishingServiceUuid === service.serviceId}
                    isDisabled={
                      unpublishingServiceUuid !== null ||
                      publishingServiceUuid !== null
                    }
                  />
                </Tooltip>
              ) : (
                <Tooltip
                  label={
                    isServiceModelDeprecated(service)
                      ? "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing."
                      : "Publish"
                  }
                  hasArrow
                  placement="top"
                >
                  <Box as="span" display="inline-block">
                    <IconButton
                      aria-label="Publish"
                      icon={<FaUpload />}
                      size="sm"
                      variant="ghost"
                      colorScheme="green"
                      _hover={{ bg: "green.50" }}
                      onClick={() => requestPublish(service)}
                      isLoading={publishingServiceUuid === service.serviceId}
                      isDisabled={
                        unpublishingServiceUuid !== null ||
                        publishingServiceUuid !== null ||
                        isServiceModelDeprecated(service)
                      }
                    />
                  </Box>
                </Tooltip>
              ))}
            {!isRegistryReadOnly && (
              <Tooltip label="Delete" placement="top" hasArrow>
                <IconButton
                  aria-label="Delete"
                  icon={<DeleteIcon />}
                  size="sm"
                  variant="ghost"
                  colorScheme="red"
                  _hover={{ bg: "red.50" }}
                  onClick={() => handleDeleteClick(service)}
                  isLoading={deletingServiceUuid === service.serviceId}
                  isDisabled={deletingServiceUuid !== null}
                />
              </Tooltip>
            )}
          </HStack>
        ),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    nameSortDirection,
    unpublishingServiceUuid,
    publishingServiceUuid,
    deletingServiceUuid,
    isRegistryReadOnly,
    availableTiers,
  ]);

  return (
    <>
      <VStack spacing={6} w="full">
        <ManagementPageHeader
          title="Services Management"
          description={
            isRegistryReadOnly
              ? "View services in the registry (read-only)"
              : "Manage and configure services"
          }
        />

        <Grid gap={8} w="full" mx="auto">
          <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
            <Tabs
              colorScheme="blue"
              variant="enclosed"
              index={activeTab}
              onChange={handleTabChange}
            >
              <TabList>
                <Tab fontWeight="semibold">Service Registry</Tab>
                {!isRegistryReadOnly && (
                  <Tab fontWeight="semibold">
                    {editingService ? "Edit Service" : "Create Service"}
                  </Tab>
                )}
                {isViewingService && (
                  <Tab fontWeight="semibold">View Service</Tab>
                )}
              </TabList>

              <TabPanels>
                {/* Service Registry Tab */}
                <TabPanel px={0} pt={6}>
                  <ServiceRegistryTab
                    cardBg={cardBg}
                    cardBorder={cardBorder}
                    items={registryTableItems}
                    columns={serviceColumns}
                    isLoading={isLoading}
                    totalServicesCount={totalServicesCount}
                    onRowClick={(service) =>
                      handleViewService(
                        service.serviceId || service.service_id || "",
                      )
                    }
                    tableKey={tableKey}
                    searchQuery={searchQuery}
                    onSearchQueryChange={setSearchQuery}
                    filterStatus={filterStatus}
                    onFilterStatusChange={setFilterStatus}
                    filterTaskType={filterTaskType}
                    onFilterTaskTypeChange={setFilterTaskType}
                    taskTypeNames={taskTypeNames}
                    hasActiveFilters={hasActiveFilters}
                    onClearFilters={clearAllFilters}
                  />
                </TabPanel>

                {/* Create/Edit Service Tab */}
                {!isRegistryReadOnly && (
                  <TabPanel px={0} pt={6}>
                    <ServiceFormTab
                      cardBg={cardBg}
                      cardBorder={cardBorder}
                      editingService={editingService}
                      formData={formData}
                      onInputChange={handleInputChange}
                      onTaskTypeChange={handleTaskTypeChange}
                      onModelNameChange={handleModelNameChange}
                      taskTypeNames={taskTypeNames}
                      isLoadingModels={isLoadingModels}
                      filteredModelsForDropdown={filteredModelsForDropdown}
                      unitType={unitType}
                      pricePerUnit={pricePerUnit}
                      onPricePerUnitChange={setPricePerUnit}
                      unitSize={unitSize}
                      onUnitSizeChange={setUnitSize}
                      selectedTiers={selectedTiers}
                      onToggleTier={toggleTier}
                      availableTiers={availableTiers}
                      isCreateFormModelSelected={isCreateFormModelSelected}
                      canCreateService={canCreateService}
                      isSubmitting={isSubmitting}
                      onSubmit={handleSubmit}
                      onCancel={handleCancelForm}
                    />
                  </TabPanel>
                )}

                {/* View Service Tab */}
                {isViewingService && selectedService ? (
                  <TabPanel px={0} pt={6}>
                    <ServiceDetailTab
                      cardBg={cardBg}
                      cardBorder={cardBorder}
                      selectedService={selectedService}
                      isRegistryReadOnly={isRegistryReadOnly}
                      getTaskColor={getTaskColor}
                      isServiceModelDeprecated={isServiceModelDeprecated}
                      selectedServiceModelDeprecated={
                        selectedServiceModelDeprecated
                      }
                      viewServiceUnitType={viewServiceUnitType}
                      unpublishingServiceUuid={unpublishingServiceUuid}
                      publishingServiceUuid={publishingServiceUuid}
                      onRequestUnpublish={requestUnpublish}
                      onRequestPublish={requestPublish}
                    />
                  </TabPanel>
                ) : null}
              </TabPanels>
            </Tabs>
          </Card>
        </Grid>
      </VStack>

      <ConfirmDialog
        isOpen={isOpen}
        onClose={onClose}
        onConfirm={handleDeleteConfirm}
        title="Delete service"
        body={
          <>
            Are you sure you want to delete the service{" "}
            <strong>
              {serviceToDelete?.name || serviceToDelete?.service_id}
            </strong>
            {"? This action cannot be undone."}
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={deletingServiceUuid === serviceToDelete?.serviceId}
        confirmLoadingText="Deleting..."
        leastDestructiveRef={cancelRef}
      />

      <ConfirmDialog
        isOpen={isPublishConfirmOpen}
        onClose={closePublishConfirm}
        onConfirm={handlePublishConfirm}
        title="Publish service"
        body={
          <>
            Are you sure you want to publish{" "}
            <strong>
              {confirmPublishService?.name || confirmPublishService?.serviceId}
            </strong>
            {"? The service will be available for use."}
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="green"
        isConfirmLoading={
          publishingServiceUuid === confirmPublishService?.serviceId
        }
        confirmLoadingText="Publishing..."
        leastDestructiveRef={cancelPublishRef}
      />

      <ConfirmDialog
        isOpen={isUnpublishConfirmOpen}
        onClose={closeUnpublishConfirm}
        onConfirm={handleUnpublishConfirm}
        title="Unpublish service"
        body={
          <>
            Are you sure you want to unpublish{" "}
            <strong>
              {confirmUnpublishService?.name ||
                confirmUnpublishService?.serviceId}
            </strong>
            {"? The service will no longer be available for use."}
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={
          unpublishingServiceUuid === confirmUnpublishService?.serviceId
        }
        confirmLoadingText="Unpublishing..."
        leastDestructiveRef={cancelUnpublishRef}
      />
    </>
  );
};

export default ServicesManagement;
