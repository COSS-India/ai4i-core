// Services Management: registry list stays mounted. Create, edit, and view use FormDrawer.
import { DeleteIcon, EditIcon } from "@chakra-ui/icons";
import { MdOutlineCheckCircle, MdOutlineUnpublished } from "react-icons/md";
import React, { useCallback, useLayoutEffect, useMemo, useState } from "react";
import ManagementPageHeader from "../common/ManagementPageHeader";
import CreateButton from "../common/CreateButton";
import FormActions from "../common/FormActions";
import FormDrawer from "../common/FormDrawer";
import { useFormPageLeave } from "../common/FormPage";
import {
  createActionsColumn,
  type DataTableAction,
  type DataTableColumn,
} from "../common/table";
import type { Service } from "../../services/servicesManagementService";
import ConfirmDialog from "../common/ConfirmDialog";
import { useAuth } from "../../hooks/useAuth";
import { useServicesManagement } from "../../hooks/useServicesManagement";
import { authService } from "../../services/authService";
import ServiceListColumnPicker from "./ServiceListColumnPicker";
import ServiceRegistryTab from "./ServiceRegistryTab";
import ServiceFormTab from "./ServiceFormTab";
import ServiceDetailTab from "./ServiceDetailTab";
import {
  defaultServiceListColumnIds,
  serviceListCellKey,
  type ServiceListColumnDef,
} from "./serviceListColumns";
import {
  loadVisibleServiceColumns,
  nextVisibleColumnIds,
  persistVisibleServiceColumns,
  resetVisibleServiceColumns,
} from "./serviceColumnPreferences";
import {
  renderEmptyServiceCell,
  renderServiceCachedInputPriceCell,
  renderServiceCreatedAtCell,
  renderServiceIdCell,
  renderServiceInputPriceCell,
  renderServiceModelNameCell,
  renderServiceNameCell,
  renderServiceOutputPriceCell,
  renderServicePublishedOnCell,
  renderServiceStatusCell,
  renderServiceTaskTypeCell,
  renderServiceTierCell,
} from "./serviceListCells";

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

type ServiceActionsContext = {
  isRegistryReadOnly: boolean;
  unpublishingServiceUuid: string | null;
  publishingServiceUuid: string | null;
  deletingServiceUuid: string | null;
  handleEditService: (serviceId: string) => void;
  handleDeleteClick: (service: Service) => void;
  requestPublish: (service: Service) => void;
  requestUnpublish: (service: Service) => void;
};

function buildPublishAction(
  service: Service,
  context: ServiceActionsContext,
): DataTableAction {
  const publishBusy =
    context.unpublishingServiceUuid !== null ||
    context.publishingServiceUuid !== null;
  if (service.isPublished === true) {
    return {
      id: "unpublish",
      label: "Unpublish",
      icon: <MdOutlineUnpublished />,
      visible: !context.isRegistryReadOnly,
      color: "red.500",
      hoverColor: "red.600",
      hoverBg: "red.50",
      onClick: () => context.requestUnpublish(service),
      isLoading: context.unpublishingServiceUuid === service.serviceId,
      disabled: publishBusy,
    };
  }
  const publishBlocked = isServiceModelDeprecated(service);
  let tooltip = "Publish";
  if (publishBlocked) {
    tooltip =
      "This service cannot be published because its associated model is deprecated. Restore the model to ACTIVE before publishing.";
  }
  return {
    id: "publish",
    label: "Publish",
    tooltip,
    icon: <MdOutlineCheckCircle />,
    visible: !context.isRegistryReadOnly,
    color: "green.500",
    hoverColor: "green.600",
    hoverBg: "green.50",
    onClick: () => context.requestPublish(service),
    isLoading: context.publishingServiceUuid === service.serviceId,
    disabled: publishBusy || publishBlocked,
  };
}

function buildServiceActions(
  service: Service,
  context: ServiceActionsContext,
): DataTableAction[] {
  const serviceId = service.serviceId || service.service_id || "";
  return [
    {
      id: "edit",
      label: "Edit",
      icon: <EditIcon />,
      visible: !context.isRegistryReadOnly,
      onClick: () => context.handleEditService(serviceId),
    },
    buildPublishAction(service, context),
    {
      id: "delete",
      label: "Delete",
      icon: <DeleteIcon />,
      visible: !context.isRegistryReadOnly,
      onClick: () => context.handleDeleteClick(service),
      isLoading: context.deletingServiceUuid === service.serviceId,
      disabled: context.deletingServiceUuid !== null,
    },
  ];
}

function buildVisibleServiceColumns(
  catalogue: readonly ServiceListColumnDef[],
  visibleColumnIds: readonly string[],
  templates: DataTableColumn<Service>[],
): DataTableColumn<Service>[] {
  const byCell = new Map(templates.map((column) => [column.id, column]));
  const built: DataTableColumn<Service>[] = [];
  let actionsColumn: DataTableColumn<Service> | null = null;
  for (const definition of catalogue) {
    if (!visibleColumnIds.includes(definition.id)) continue;
    const cellKey = serviceListCellKey(definition.id);
    const template = byCell.get(cellKey);
    const column: DataTableColumn<Service> = template
      ? {
          ...template,
          id: definition.id,
          header: definition.label,
          sortable: definition.sortable !== false && Boolean(template.sortable),
        }
      : {
          id: definition.id,
          header: definition.label,
          sortable: false,
          cell: renderEmptyServiceCell,
        };
    if (cellKey === "actions") {
      actionsColumn = column;
    } else {
      built.push(column);
    }
  }
  if (actionsColumn) built.push(actionsColumn);
  return built;
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
    serviceListCatalogue,
    serviceListUsesServer,
    registryPage,
    registryPageSize,
    setRegistryPage,
    setRegistryPageSize,
    serverFilters,
    setServerFilterValue,
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
  const [visibleColumnIds, setVisibleColumnIds] = useState<string[]>(
    defaultServiceListColumnIds,
  );
  const catalogueKey = serviceListCatalogue.map((column) => column.id).join("|");

  const preferenceUserId = useCallback(
    () => userId || authService.getStoredUser()?.user_id || "",
    [userId],
  );

  useLayoutEffect(() => {
    const id = preferenceUserId();
    if (!id) return;
    let cancelled = false;
    void loadVisibleServiceColumns({
      userId: id,
      usesServer: serviceListUsesServer,
      catalogue: serviceListCatalogue,
    }).then((next) => {
      if (cancelled) return;
      setVisibleColumnIds((current) => nextVisibleColumnIds(current, next));
    });
    return () => {
      cancelled = true;
    };
  }, [preferenceUserId, serviceListUsesServer, catalogueKey, serviceListCatalogue]);

  const handleRegistrySortChange = useCallback(
    (next: { key: string; direction: "asc" | "desc" }) => {
      if (serviceListUsesServer) setRegistryPage(1);
      registrySort.onSortChange(next);
    },
    [registrySort, serviceListUsesServer, setRegistryPage],
  );

  const resetSortIfColumnHidden = useCallback(
    (visibleIds: readonly string[]) => {
      if (registrySort.mode !== "sorted" || !registrySort.sort.key) return;
      if (visibleIds.includes(registrySort.sort.key)) return;
      handleRegistrySortChange({ key: "name", direction: "asc" });
    },
    [handleRegistrySortChange, registrySort.mode, registrySort.sort.key],
  );

  const applyVisibleColumns = useCallback(
    (next: readonly string[]) => {
      const resolved = persistVisibleServiceColumns({
        userId: preferenceUserId(),
        usesServer: serviceListUsesServer,
        catalogue: serviceListCatalogue,
        columnIds: next,
      });
      setVisibleColumnIds(resolved);
      resetSortIfColumnHidden(resolved);
    },
    [
      preferenceUserId,
      resetSortIfColumnHidden,
      serviceListCatalogue,
      serviceListUsesServer,
    ],
  );

  const resetVisibleColumns = useCallback(() => {
    const defaults = resetVisibleServiceColumns({
      userId: preferenceUserId(),
      usesServer: serviceListUsesServer,
      catalogue: serviceListCatalogue,
    });
    setVisibleColumnIds(defaults);
    resetSortIfColumnHidden(defaults);
  }, [
    preferenceUserId,
    resetSortIfColumnHidden,
    serviceListCatalogue,
    serviceListUsesServer,
  ]);

  const actionsContext = useMemo(
    (): ServiceActionsContext => ({
      isRegistryReadOnly,
      unpublishingServiceUuid,
      publishingServiceUuid,
      deletingServiceUuid,
      handleEditService,
      handleDeleteClick,
      requestPublish,
      requestUnpublish,
    }),
    [
      isRegistryReadOnly,
      unpublishingServiceUuid,
      publishingServiceUuid,
      deletingServiceUuid,
      handleEditService,
      handleDeleteClick,
      requestPublish,
      requestUnpublish,
    ],
  );

  const columnTemplates = useMemo((): DataTableColumn<Service>[] => {
    const columns: DataTableColumn<Service>[] = [
      {
        id: "name",
        header: "Name",
        sortable: true,
        sortAccessor: (service) => service.name ?? "",
        cell: renderServiceNameCell,
      },
      {
        id: "task",
        header: "Model Task Type",
        sortable: true,
        cell: renderServiceTaskTypeCell,
      },
      {
        id: "tier",
        header: "Tier",
        sortable: true,
        truncate: false,
        cell: renderServiceTierCell,
      },
      {
        id: "status",
        header: "Status",
        sortable: true,
        cell: renderServiceStatusCell,
      },
      {
        id: "createdAt",
        header: "Created At",
        sortable: true,
        cell: renderServiceCreatedAtCell,
      },
      {
        id: "modelName",
        header: "Model Name",
        sortable: true,
        cell: renderServiceModelNameCell,
      },
      {
        id: "serviceId",
        header: "Service ID",
        sortable: true,
        cell: renderServiceIdCell,
      },
      {
        id: "inputPrice",
        header: "Input Price",
        sortable: true,
        isNumeric: true,
        cell: renderServiceInputPriceCell,
      },
      {
        id: "outputPrice",
        header: "Output Price",
        sortable: true,
        isNumeric: true,
        cell: renderServiceOutputPriceCell,
      },
      {
        id: "cachedInputPrice",
        header: "Cached Input Price",
        sortable: true,
        isNumeric: true,
        cell: renderServiceCachedInputPriceCell,
      },
      {
        id: "publishedOn",
        header: "Published On",
        sortable: true,
        cell: renderServicePublishedOnCell,
      },
      createActionsColumn<Service>({
        getActions: (service) => buildServiceActions(service, actionsContext),
      }),
    ];
    return columns;
  }, [actionsContext]);

  const serviceColumns = useMemo(
    () =>
      buildVisibleServiceColumns(
        serviceListCatalogue,
        visibleColumnIds,
        columnTemplates,
      ),
    [columnTemplates, serviceListCatalogue, visibleColumnIds],
  );

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
  let pageDescription =
    "Find a service, open it to view or edit, or create a new one. Publish when it should appear for users.";
  if (isRegistryReadOnly) {
    pageDescription =
      "Browse services in the registry. You can open a service to view its configuration.";
  }
  const showCreateAction = !isRegistryReadOnly && !isCreateServiceTabDisabled;

  return (
    <>
      <ManagementPageHeader
        crumbs={false}
        title="Services Management"
        description={pageDescription}
        actions={
          showCreateAction ? (
            <CreateButton onClick={openCreateModal}>Create Service</CreateButton>
          ) : undefined
        }
      />
      <ServiceRegistryTab
        items={registryTableItems}
        columns={serviceColumns}
        sort={registrySort.sort}
        onSortChange={handleRegistrySortChange}
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
        serverColumns={serviceListUsesServer ? serviceListCatalogue : undefined}
        serverFilterValues={serverFilters}
        onServerFilterChange={serviceListUsesServer ? setServerFilterValue : undefined}
        serverPage={registryPage}
        serverPageSize={registryPageSize}
        serverTotal={totalServicesCount}
        onServerPageChange={serviceListUsesServer ? setRegistryPage : undefined}
        onServerPageSizeChange={serviceListUsesServer ? setRegistryPageSize : undefined}
        columnPicker={
          <ServiceListColumnPicker
            columns={serviceListCatalogue}
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
