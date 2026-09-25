// Services Management: Registry and View Service tabs. Create and Edit use modals.
import {
  Badge,
  Box,
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
import { DeleteIcon, EditIcon } from "@chakra-ui/icons";
import { MdOutlineCheckCircle, MdOutlineUnpublished } from "react-icons/md";
import React, { useMemo } from "react";
import ManagementPageHeader from "../common/ManagementPageHeader";
import CreateButton from "../common/CreateButton";
import FormActions from "../common/FormActions";
import { useAdminTableSurface, type DataTableColumn } from "../common/table";
import type { Service } from "../../services/servicesManagementService";
import ConfirmDialog from "../common/ConfirmDialog";
import { useServicesManagement } from "../../hooks/useServicesManagement";
import ServiceRegistryTab from "./ServiceRegistryTab";
import ServiceFormTab from "./ServiceFormTab";
import ServiceDetailTab from "./ServiceDetailTab";
import StandardModal, { CreateModal } from "../common/StandardModal";
import { getTaskColorScheme } from "../../config/constants";
import { resolveTaskType } from "../../utils/platformService";

const CREATE_SERVICE_FORM_ID = "create-service-form";
const EDIT_SERVICE_FORM_ID = "edit-service-form";

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
    filterTier,
    setFilterTier,
    tierFilterOptions,
    hasActiveFilters,
    clearAllFilters,
    registrySort,
    handleViewService,
    handleEditService,
    handleDeleteClick,
    deletingServiceUuid,
    editingService,
    formData,
    handleInputChange,
    handleTaskTypeChange,
    handleModelNameChange,
    authToken,
    setAuthToken,
    hasAuthToken,
    savedAuthTokenMask,
    isLoadingModels,
    filteredModelsForDropdown,
    unitType,
    pricePerUnit,
    setPricePerUnit,
    pricePerUnitError,
    unitSize,
    setUnitSize,
    currency,
    setCurrency,
    selectedTiers,
    toggleTier,
    availableTiers,
    isCreateServiceTabDisabled,
    isCreateFormModelSelected,
    canCreateService,
    isLlmTaskType,
    serviceIdError,
    serviceIdLengthError,
    serviceDescriptionError,
    serviceNameError,
    hardwareDescriptionError,
    createFormEpoch,
    isSubmitting,
    handleSubmit,
    handleCancelForm,
    isCreateOpen,
    openCreateModal,
    closeCreateModal,
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

  const serviceColumns = useMemo((): DataTableColumn<Service>[] => {
    return [
      {
        id: "name",
        header: "Name",
        sortable: true,
        sortAccessor: (service) => service.name ?? "",
        cell: (service) => (
          <Text fontSize="sm" fontWeight="medium" noOfLines={1} title={service.name}>
            {service.name || "N/A"}
          </Text>
        ),
      },
      {
        id: "task",
        header: "Model Task Type",
        cell: (service) => {
          const taskType = resolveTaskType(service);
          return (
            <Badge colorScheme={getTaskColorScheme(taskType)} fontSize="sm" p={1}>
              {taskType ? taskType.toUpperCase() : "N/A"}
            </Badge>
          );
        },
      },
      {
        id: "tiers",
        header: "Tiers",
        sortable: true,
        sortAccessor: (service) =>
          (service.tierNames ?? service.tiers ?? []).join(", ").toLowerCase(),
        cell: (service) => {
          const names = service.tierNames;
          if (!names || names.length === 0) {
            return (
              <Text fontSize="sm" color="ink.400">
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
        sortable: true,
        sortAccessor: (service) =>
          service.createdAt ? new Date(service.createdAt).getTime() : 0,
        cell: (service) => (
          <Text fontSize="sm" color="ink.600">
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
            {!isRegistryReadOnly && (
              <Tooltip label="Edit" placement="top" hasArrow>
                <IconButton
                  aria-label="Edit"
                  icon={<EditIcon />}
                  size="sm"
                  variant="ghost"
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
                    icon={<MdOutlineUnpublished />}
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
                      icon={<MdOutlineCheckCircle />}
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
              ? "Browse services in the registry. You can open a service to view its configuration."
              : "Find a service, open it to view or edit, or create a new one. Publish when it should appear for users."
          }
          actions={
            !isRegistryReadOnly &&
            !editingService &&
            !isCreateServiceTabDisabled ? (
              <CreateButton onClick={openCreateModal}>
                Create Service
              </CreateButton>
            ) : undefined
          }
        />

            <Tabs
              w="full"
              colorScheme="blue"
              variant="enclosed"
              index={activeTab}
              onChange={handleTabChange}
            >
              <TabList>
                <Tab fontWeight="semibold">Service Registry</Tab>
                {isViewingService && (
                  <Tab fontWeight="semibold">View Service</Tab>
                )}
              </TabList>

              <TabPanels>
                {/* Service Registry Tab */}
                <TabPanel>
                  <ServiceRegistryTab
                    items={registryTableItems}
                    columns={serviceColumns}
                    sort={registrySort.sort}
                    onSortChange={registrySort.onSortChange}
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
                    filterTier={filterTier}
                    onFilterTierChange={setFilterTier}
                    tierFilterOptions={tierFilterOptions}
                    hasActiveFilters={hasActiveFilters}
                    onClearFilters={clearAllFilters}
                  />
                </TabPanel>

                {/* View Service Tab */}
                {isViewingService && selectedService ? (
                  <TabPanel>
                    <ServiceDetailTab
                      cardBg={cardBg}
                      cardBorder={cardBorder}
                      selectedService={selectedService}
                      isRegistryReadOnly={isRegistryReadOnly}
                      getTaskColor={getTaskColorScheme}
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
      </VStack>

      <CreateModal
        isOpen={isCreateOpen}
        onClose={closeCreateModal}
        size="xl"
        title="Create Service"
        description="Register a service and map it to a model and tiers."
        footer={
          <FormActions
            cancelLabel="Reset"
            submitLabel="Create Service"
            onCancel={handleCancelForm}
            submitType="submit"
            form={CREATE_SERVICE_FORM_ID}
            isLoading={isSubmitting}
            loadingText="Creating..."
            isDisabled={!canCreateService || isSubmitting}
            justify="space-between"
            pt={0}
          />
        }
      >
        <ServiceFormTab
          key={createFormEpoch}
          cardBg={cardBg}
          cardBorder={cardBorder}
          editingService={null}
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
          pricePerUnitError={pricePerUnitError}
          unitSize={unitSize}
          onUnitSizeChange={setUnitSize}
          currency={currency}
          onCurrencyChange={setCurrency}
          selectedTiers={selectedTiers}
          onToggleTier={toggleTier}
          availableTiers={availableTiers}
          isCreateFormModelSelected={isCreateFormModelSelected}
          canCreateService={canCreateService}
          isLlmTaskType={isLlmTaskType}
          authToken={authToken}
          onAuthTokenChange={setAuthToken}
          hasAuthToken={hasAuthToken}
          savedAuthTokenMask={savedAuthTokenMask}
          serviceIdError={serviceIdError}
          serviceIdLengthError={serviceIdLengthError}
          serviceDescriptionError={serviceDescriptionError}
          serviceNameError={serviceNameError}
          hardwareDescriptionError={hardwareDescriptionError}
          isSubmitting={isSubmitting}
          onSubmit={handleSubmit}
          onCancel={handleCancelForm}
          embedded={false}
          hideActions
          formId={CREATE_SERVICE_FORM_ID}
        />
      </CreateModal>

      <StandardModal
        isOpen={Boolean(editingService) && !isRegistryReadOnly}
        onClose={handleCancelForm}
        size="5xl"
        scrollBehavior="inside"
        title="Edit Service"
        description="Update pricing and tier mapping. Service metadata is read-only."
        modalProps={{ blockScrollOnMount: true }}
        headerProps={{ px: 6, pt: 5, pb: 4 }}
        bodyProps={{ px: 6, py: 5 }}
        footerProps={{ px: 6, py: 4 }}
        footer={
          <FormActions
            submitLabel="Save Changes"
            onCancel={handleCancelForm}
            submitType="submit"
            form={EDIT_SERVICE_FORM_ID}
            isLoading={isSubmitting}
            loadingText="Saving..."
            isDisabled={!canCreateService || isSubmitting}
            justify="space-between"
            pt={0}
          />
        }
      >
        {editingService ? (
          <ServiceFormTab
            key={createFormEpoch}
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
            pricePerUnitError={pricePerUnitError}
            unitSize={unitSize}
            onUnitSizeChange={setUnitSize}
            currency={currency}
            onCurrencyChange={setCurrency}
            selectedTiers={selectedTiers}
            onToggleTier={toggleTier}
            availableTiers={availableTiers}
            isCreateFormModelSelected={isCreateFormModelSelected}
            canCreateService={canCreateService}
            isLlmTaskType={isLlmTaskType}
            authToken={authToken}
            onAuthTokenChange={setAuthToken}
            hasAuthToken={hasAuthToken}
            savedAuthTokenMask={savedAuthTokenMask}
            serviceIdError={serviceIdError}
            serviceIdLengthError={serviceIdLengthError}
            serviceDescriptionError={serviceDescriptionError}
            serviceNameError={serviceNameError}
            hardwareDescriptionError={hardwareDescriptionError}
            isSubmitting={isSubmitting}
            onSubmit={handleSubmit}
            onCancel={handleCancelForm}
            embedded={false}
            hideActions
            formId={EDIT_SERVICE_FORM_ID}
          />
        ) : null}
      </StandardModal>

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
