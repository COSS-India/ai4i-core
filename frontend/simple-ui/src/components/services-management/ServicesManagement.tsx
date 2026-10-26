// Services Management: registry list stays mounted. Create, edit, and view use FormDrawer.
import {
  Badge,
  HStack,
  Text,
  VStack,
} from "@chakra-ui/react";
import { DeleteIcon, EditIcon } from "@chakra-ui/icons";
import { MdOutlineCheckCircle, MdOutlineUnpublished } from "react-icons/md";
import React, { useCallback, useLayoutEffect, useMemo, useState } from "react";
import ManagementPageHeader from "../common/ManagementPageHeader";
import CreateButton from "../common/CreateButton";
import FormActions from "../common/FormActions";
import FormDrawer from "../common/FormDrawer";
import { useFormPageLeave } from "../common/FormPage";
import { createActionsColumn, type DataTableColumn } from "../common/table";
import type { Service } from "../../services/servicesManagementService";
import ConfirmDialog from "../common/ConfirmDialog";
import { useAuth } from "../../hooks/useAuth";
import { useServicesManagement } from "../../hooks/useServicesManagement";
import { authService } from "../../services/authService";
import ServiceListColumnPicker from "./ServiceListColumnPicker";
import ServiceRegistryTab from "./ServiceRegistryTab";
import ServiceFormTab from "./ServiceFormTab";
import ServiceDetailTab from "./ServiceDetailTab";
import { getTaskColorScheme } from "../../config/constants";
import { resolveTaskType } from "../../utils/platformService";
import {
  defaultServiceListColumnIds,
  formatServiceListDate,
  formatServiceListPrice,
  loadServiceListColumns,
  saveServiceListColumns,
  serviceCreatedAtMillis,
  serviceListServiceId,
  serviceModelName,
  servicePublishedOnMillis,
  type ServiceListColumnId,
} from "./serviceListColumns";

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
  const {
    isRegistryReadOnly,
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
    cachedInputPricePerUnit,
    setCachedInputPricePerUnit,
    cachedInputPricePerUnitError,
    outputPricePerUnit,
    setOutputPricePerUnit,
    outputPricePerUnitError,
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
    releaseCreateForm,
    createReturnTo,
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

  const leaveCreateToCaller = useFormPageLeave(
    createReturnTo ? { href: createReturnTo } : undefined,
    releaseCreateForm,
  );

  const { user } = useAuth();
  const userId = user?.user_id ?? "";
  const [visibleColumnIds, setVisibleColumnIds] = useState<ServiceListColumnId[]>(
    defaultServiceListColumnIds,
  );

  const preferenceUserId = useCallback(
    () => userId || authService.getStoredUser()?.user_id || "",
    [userId],
  );

  useLayoutEffect(() => {
    const id = preferenceUserId();
    if (!id) return;
    setVisibleColumnIds((current) => {
      const next = loadServiceListColumns(id);
      if (current.length === next.length && current.every((columnId, index) => columnId === next[index])) {
        return current;
      }
      return next;
    });
  }, [preferenceUserId]);

  const applyVisibleColumns = useCallback(
    (next: readonly ServiceListColumnId[]) => {
      setVisibleColumnIds(saveServiceListColumns(preferenceUserId(), next));
    },
    [preferenceUserId],
  );

  const resetVisibleColumns = useCallback(() => {
    applyVisibleColumns(defaultServiceListColumnIds());
  }, [applyVisibleColumns]);

  const serviceColumns = useMemo((): DataTableColumn<Service>[] => {
    const columns: DataTableColumn<Service>[] = [
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
        id: "modelTaskType",
        header: "Model Task Type",
        sortable: true,
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
        id: "tier",
        header: "Tier",
        sortable: true,
        truncate: false,
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
        sortable: true,
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
        id: "createdAt",
        header: "Created At",
        sortable: true,
        cell: (service) => {
          const label = formatServiceListDate(serviceCreatedAtMillis(service));
          return (
            <Text fontSize="sm" color={label === "—" ? "ink.400" : undefined} noOfLines={1}>
              {label}
            </Text>
          );
        },
      },
      {
        id: "modelName",
        header: "Model Name",
        sortable: true,
        cell: (service) => {
          const label = serviceModelName(service) || "—";
          return (
            <Text
              fontSize="sm"
              color={label === "—" ? "ink.400" : undefined}
              noOfLines={1}
              title={label}
            >
              {label}
            </Text>
          );
        },
      },
      {
        id: "serviceId",
        header: "Service ID",
        sortable: true,
        cell: (service) => {
          const label = serviceListServiceId(service) || "—";
          return (
            <Text
              fontSize="sm"
              color={label === "—" ? "ink.400" : undefined}
              noOfLines={1}
              title={label}
            >
              {label}
            </Text>
          );
        },
      },
      {
        id: "inputPrice",
        header: "Input Price",
        sortable: true,
        isNumeric: true,
        cell: (service) => (
          <Text fontSize="sm" color={service.costPerUnit == null ? "ink.400" : undefined}>
            {formatServiceListPrice(service.costPerUnit)}
          </Text>
        ),
      },
      {
        id: "outputPrice",
        header: "Output Price",
        sortable: true,
        isNumeric: true,
        cell: (service) => (
          <Text fontSize="sm" color={service.outputCostPerUnit == null ? "ink.400" : undefined}>
            {formatServiceListPrice(service.outputCostPerUnit)}
          </Text>
        ),
      },
      {
        id: "cachedInputPrice",
        header: "Cached Input Price",
        sortable: true,
        isNumeric: true,
        cell: (service) => (
          <Text
            fontSize="sm"
            color={service.cachedInputCostPerUnit == null ? "ink.400" : undefined}
          >
            {formatServiceListPrice(service.cachedInputCostPerUnit)}
          </Text>
        ),
      },
      {
        id: "publishedOn",
        header: "Published On",
        sortable: true,
        cell: (service) => {
          const label = formatServiceListDate(servicePublishedOnMillis(service));
          return (
            <Text fontSize="sm" color={label === "—" ? "ink.400" : undefined} noOfLines={1}>
              {label}
            </Text>
          );
        },
      },
      createActionsColumn<Service>({
        getActions: (service) => {
          const publishBlocked = isServiceModelDeprecated(service);
          const publishBusy =
            unpublishingServiceUuid !== null || publishingServiceUuid !== null;
          return [
            {
              id: "edit",
              label: "Edit",
              icon: <EditIcon />,
              visible: !isRegistryReadOnly,
              onClick: () =>
                handleEditService(service.serviceId || service.service_id || ""),
            },
            service.isPublished === true
              ? {
                  id: "unpublish",
                  label: "Unpublish",
                  icon: <MdOutlineUnpublished />,
                  visible: !isRegistryReadOnly,
                  color: "red.500",
                  hoverColor: "red.600",
                  hoverBg: "red.50",
                  onClick: () => requestUnpublish(service),
                  isLoading: unpublishingServiceUuid === service.serviceId,
                  disabled: publishBusy,
                }
              : {
                  id: "publish",
                  label: "Publish",
                  tooltip: publishBlocked
                    ? "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing."
                    : "Publish",
                  icon: <MdOutlineCheckCircle />,
                  visible: !isRegistryReadOnly,
                  color: "green.500",
                  hoverColor: "green.600",
                  hoverBg: "green.50",
                  onClick: () => requestPublish(service),
                  isLoading: publishingServiceUuid === service.serviceId,
                  disabled: publishBusy || publishBlocked,
                },
            {
              id: "delete",
              label: "Delete",
              icon: <DeleteIcon />,
              visible: !isRegistryReadOnly,
              onClick: () => handleDeleteClick(service),
              isLoading: deletingServiceUuid === service.serviceId,
              disabled: deletingServiceUuid !== null,
            },
          ];
        },
      }),
    ];
    const byId = new Map(columns.map((column) => [column.id, column]));
    return visibleColumnIds.flatMap((id) => {
      const column = byId.get(id);
      return column ? [column] : [];
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    unpublishingServiceUuid,
    publishingServiceUuid,
    deletingServiceUuid,
    isRegistryReadOnly,
    availableTiers,
    visibleColumnIds,
  ]);

  const serviceForm = (
    <ServiceFormTab
      key={createFormEpoch}
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
      cachedInputPricePerUnit={cachedInputPricePerUnit}
      onCachedInputPricePerUnitChange={setCachedInputPricePerUnit}
      cachedInputPricePerUnitError={cachedInputPricePerUnitError}
      outputPricePerUnit={outputPricePerUnit}
      onOutputPricePerUnitChange={setOutputPricePerUnit}
      outputPricePerUnitError={outputPricePerUnitError}
      unitSize={unitSize}
      onUnitSizeChange={setUnitSize}
      currency={currency}
      onCurrencyChange={setCurrency}
      selectedTiers={selectedTiers}
      onToggleTier={toggleTier}
      availableTiers={availableTiers}
      isCreateFormModelSelected={isCreateFormModelSelected}
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
      onSubmit={handleSubmit}
      formId={editingService ? EDIT_SERVICE_FORM_ID : CREATE_SERVICE_FORM_ID}
    />
  );

  const showServiceView = Boolean(isViewingService && selectedService);
  const showServiceEdit = Boolean(editingService) && !isRegistryReadOnly && !showServiceView;
  const showServiceCreate = isCreateOpen && !showServiceEdit && !showServiceView;

  return (
    <>
      <ManagementPageHeader
        crumbs={false}
        title="Services Management"
        description={
          isRegistryReadOnly
            ? "Browse services in the registry. You can open a service to view its configuration."
            : "Find a service, open it to view or edit, or create a new one. Publish when it should appear for users."
        }
        actions={
          !isRegistryReadOnly && !isCreateServiceTabDisabled ? (
            <CreateButton onClick={openCreateModal}>Create Service</CreateButton>
          ) : undefined
        }
      />
      <ServiceRegistryTab
        items={registryTableItems}
        columns={serviceColumns}
        sort={registrySort.sort}
        onSortChange={registrySort.onSortChange}
        isLoading={isLoading}
        totalServicesCount={totalServicesCount}
        onRowClick={(service) =>
          handleViewService(service.serviceId || service.service_id || "")
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
        columnPicker={
          <ServiceListColumnPicker
            visibleIds={visibleColumnIds}
            onChange={applyVisibleColumns}
            onReset={resetVisibleColumns}
          />
        }
      />
      <FormDrawer
        isOpen={showServiceCreate}
        onClose={closeCreateModal}
        lockDismiss={isSubmitting}
        size="wide"
        title="Create Service"
        description="Register a service and map it to a model and tiers."
        footer={
          <FormActions
            cancelLabel="Cancel"
            submitLabel="Create Service"
            onCancel={createReturnTo ? leaveCreateToCaller : closeCreateModal}
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
        {showServiceCreate ? serviceForm : null}
      </FormDrawer>
      {showServiceView && selectedService ? (
        <ServiceDetailTab
          selectedService={selectedService}
          isRegistryReadOnly={isRegistryReadOnly}
          isServiceModelDeprecated={isServiceModelDeprecated}
          selectedServiceModelDeprecated={selectedServiceModelDeprecated}
          viewServiceUnitType={viewServiceUnitType}
          unpublishingServiceUuid={unpublishingServiceUuid}
          publishingServiceUuid={publishingServiceUuid}
          onRequestUnpublish={requestUnpublish}
          onRequestPublish={requestPublish}
          onClose={() => handleTabChange(0)}
        />
      ) : null}
      <FormDrawer
        isOpen={showServiceEdit}
        onClose={handleCancelForm}
        lockDismiss={isSubmitting}
        size="wide"
        title={
          editingService?.name ||
          editingService?.serviceId ||
          editingService?.service_id ||
          "Edit Service"
        }
        description="Update pricing and tier mapping. Service metadata is read-only."
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
        {showServiceEdit ? serviceForm : null}
      </FormDrawer>

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
