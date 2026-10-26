// Services Management: registry list stays mounted. Create, edit, and view use FormDrawer.
import { DeleteIcon, EditIcon } from "@chakra-ui/icons";
import { MdOutlineCheckCircle, MdOutlineUnpublished } from "react-icons/md";
import React, { useMemo } from "react";
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
import ServiceListColumnPicker from "./ServiceListColumnPicker";
import ServiceRegistryTab from "./ServiceRegistryTab";
import ServiceFormTab from "./ServiceFormTab";
import ServiceDetailTab from "./ServiceDetailTab";
import {
  serviceListCellKey,
  type ServiceListColumnDef,
} from "./serviceListColumns";
import { useServiceListVisibleColumns } from "./useServiceListVisibleColumns";
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

const READ_ONLY_PAGE_DESCRIPTION =
  "Browse services in the registry. You can open a service to view its configuration.";
const EDITOR_PAGE_DESCRIPTION =
  "Find a service, open it to view or edit, or create a new one. Publish when it should appear for users.";

function pageDescriptionForRole(isRegistryReadOnly: boolean): string {
  if (isRegistryReadOnly) return READ_ONLY_PAGE_DESCRIPTION;
  return EDITOR_PAGE_DESCRIPTION;
}

function serviceRowId(service: Service): string {
  return service.serviceId || service.service_id || "";
}

function resolveDrawerFlags(options: {
  isViewingService: boolean;
  selectedService: Service | null;
  editingService: Service | null;
  isRegistryReadOnly: boolean;
  isCreateOpen: boolean;
  isCreateServiceTabDisabled: boolean;
}): {
  showServiceView: boolean;
  showServiceEdit: boolean;
  showServiceCreate: boolean;
  showCreateAction: boolean;
} {
  const showServiceView = Boolean(
    options.isViewingService && options.selectedService,
  );
  const showServiceEdit =
    Boolean(options.editingService) &&
    !options.isRegistryReadOnly &&
    !showServiceView;
  const showServiceCreate =
    options.isCreateOpen && !showServiceEdit && !showServiceView;
  const showCreateAction =
    !options.isRegistryReadOnly && !options.isCreateServiceTabDisabled;
  return {
    showServiceView,
    showServiceEdit,
    showServiceCreate,
    showCreateAction,
  };
}

function serverRegistryProps(options: {
  usesServer: boolean;
  catalogue: readonly ServiceListColumnDef[];
  setServerFilterValue: (columnId: string, value: string) => void;
  setRegistryPage: (page: number) => void;
  setRegistryPageSize: (size: number) => void;
}): {
  serverColumns: readonly ServiceListColumnDef[] | undefined;
  onServerFilterChange: ((columnId: string, value: string) => void) | undefined;
  onServerPageChange: ((page: number) => void) | undefined;
  onServerPageSizeChange: ((size: number) => void) | undefined;
} {
  if (!options.usesServer) {
    return {
      serverColumns: undefined,
      onServerFilterChange: undefined,
      onServerPageChange: undefined,
      onServerPageSizeChange: undefined,
    };
  }
  return {
    serverColumns: options.catalogue,
    onServerFilterChange: options.setServerFilterValue,
    onServerPageChange: options.setRegistryPage,
    onServerPageSizeChange: options.setRegistryPageSize,
  };
}

function createLeaveHref(
  createReturnTo: string | null,
): { href: string } | undefined {
  if (!createReturnTo) return undefined;
  return { href: createReturnTo };
}

function pickCreateCancelHandler(
  createReturnTo: string | null,
  leaveToCaller: () => void,
  closeCreate: () => void,
): () => void {
  if (createReturnTo) return leaveToCaller;
  return closeCreate;
}

function whenTrue<T>(condition: boolean, value: T): T | undefined {
  if (!condition) return undefined;
  return value;
}

function whenTrueNode(
  condition: boolean,
  node: React.ReactNode,
): React.ReactNode {
  if (!condition) return null;
  return node;
}

function serviceLabel(
  service: { name?: string; serviceId?: string; service_id?: string } | null,
  fallback: string,
): string {
  if (!service) return fallback;
  if (service.name) return service.name;
  if (service.serviceId) return service.serviceId;
  if (service.service_id) return service.service_id;
  return fallback;
}

function formActionsDisabled(
  canCreateService: boolean,
  isSubmitting: boolean,
): boolean {
  if (isSubmitting) return true;
  return !canCreateService;
}

function isSameServiceId(
  left: string | null | undefined,
  right: string | null | undefined,
): boolean {
  if (!left || !right) return false;
  return left === right;
}

function buildServiceDetailDrawer(options: {
  show: boolean;
  selectedService: Service | null;
  isRegistryReadOnly: boolean;
  selectedServiceModelDeprecated: boolean | null;
  viewServiceUnitType: string;
  unpublishingServiceUuid: string | null;
  publishingServiceUuid: string | null;
  onRequestUnpublish: (service: Service) => void;
  onRequestPublish: (service: Service) => void;
  onClose: () => void;
}): React.ReactNode {
  if (!options.show) return null;
  if (!options.selectedService) return null;
  return (
    <ServiceDetailTab
      selectedService={options.selectedService}
      isRegistryReadOnly={options.isRegistryReadOnly}
      isServiceModelDeprecated={isServiceModelDeprecated}
      selectedServiceModelDeprecated={options.selectedServiceModelDeprecated}
      viewServiceUnitType={options.viewServiceUnitType}
      unpublishingServiceUuid={options.unpublishingServiceUuid}
      publishingServiceUuid={options.publishingServiceUuid}
      onRequestUnpublish={options.onRequestUnpublish}
      onRequestPublish={options.onRequestPublish}
      onClose={options.onClose}
    />
  );
}

const CREATE_SERVICE_FORM_ID = "create-service-form";
const EDIT_SERVICE_FORM_ID = "edit-service-form";

// Form id helpers sit below the constants they reference.
function serviceFormId(editingService: Service | null): string {
  if (editingService) return EDIT_SERVICE_FORM_ID;
  return CREATE_SERVICE_FORM_ID;
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
    createLeaveHref(createReturnTo),
    releaseCreateForm,
  );
  const createCancelHandler = pickCreateCancelHandler(
    createReturnTo,
    leaveCreateToCaller,
    closeCreateModal,
  );

  const { user } = useAuth();
  const {
    visibleColumnIds,
    applyVisibleColumns,
    resetVisibleColumns,
    handleRegistrySortChange,
  } = useServiceListVisibleColumns({
    userId: user?.user_id ?? "",
    serviceListCatalogue,
    serviceListUsesServer,
    registrySort,
    setRegistryPage,
  });

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
        actionCount: actionsContext.isRegistryReadOnly ? 0 : 3,
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
      formId={serviceFormId(editingService)}
    />
  );

  const {
    showServiceView,
    showServiceEdit,
    showServiceCreate,
    showCreateAction,
  } = resolveDrawerFlags({
    isViewingService,
    selectedService,
    editingService,
    isRegistryReadOnly,
    isCreateOpen,
    isCreateServiceTabDisabled,
  });
  const pageDescription = pageDescriptionForRole(isRegistryReadOnly);
  const serverProps = serverRegistryProps({
    usesServer: serviceListUsesServer,
    catalogue: serviceListCatalogue,
    setServerFilterValue,
    setRegistryPage,
    setRegistryPageSize,
  });
  const actionsDisabled = formActionsDisabled(canCreateService, isSubmitting);
  const createAction = whenTrue(
    showCreateAction,
    <CreateButton onClick={openCreateModal}>Create Service</CreateButton>,
  );
  const createDrawerBody = whenTrueNode(showServiceCreate, serviceForm);
  const editDrawerBody = whenTrueNode(showServiceEdit, serviceForm);
  const detailDrawer = buildServiceDetailDrawer({
    show: showServiceView,
    selectedService,
    isRegistryReadOnly,
    selectedServiceModelDeprecated,
    viewServiceUnitType,
    unpublishingServiceUuid,
    publishingServiceUuid,
    onRequestUnpublish: requestUnpublish,
    onRequestPublish: requestPublish,
    onClose: () => handleTabChange(0),
  });

  return (
    <>
      <ManagementPageHeader
        crumbs={false}
        title="Services Management"
        description={pageDescription}
        actions={createAction}
      />
      <ServiceRegistryTab
        items={registryTableItems}
        columns={serviceColumns}
        sort={registrySort.sort}
        onSortChange={handleRegistrySortChange}
        isLoading={isLoading}
        totalServicesCount={totalServicesCount}
        onRowClick={(service) => handleViewService(serviceRowId(service))}
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
        serverColumns={serverProps.serverColumns}
        serverFilterValues={serverFilters}
        onServerFilterChange={serverProps.onServerFilterChange}
        serverPage={registryPage}
        serverPageSize={registryPageSize}
        serverTotal={totalServicesCount}
        onServerPageChange={serverProps.onServerPageChange}
        onServerPageSizeChange={serverProps.onServerPageSizeChange}
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
            onCancel={createCancelHandler}
            submitType="submit"
            form={CREATE_SERVICE_FORM_ID}
            isLoading={isSubmitting}
            loadingText="Creating..."
            isDisabled={actionsDisabled}
            justify="space-between"
            pt={0}
          />
        }
      >
        {createDrawerBody}
      </FormDrawer>
      {detailDrawer}
      <FormDrawer
        isOpen={showServiceEdit}
        onClose={handleCancelForm}
        lockDismiss={isSubmitting}
        size="wide"
        title={serviceLabel(editingService, "Edit Service")}
        description="Update pricing and tier mapping. Service metadata is read-only."
        footer={
          <FormActions
            submitLabel="Save Changes"
            onCancel={handleCancelForm}
            submitType="submit"
            form={EDIT_SERVICE_FORM_ID}
            isLoading={isSubmitting}
            loadingText="Saving..."
            isDisabled={actionsDisabled}
            justify="space-between"
            pt={0}
          />
        }
      >
        {editDrawerBody}
      </FormDrawer>

      <ConfirmDialog
        isOpen={isOpen}
        onClose={onClose}
        onConfirm={handleDeleteConfirm}
        title="Delete service"
        body={
          <>
            Are you sure you want to delete the service{" "}
            <strong>{serviceLabel(serviceToDelete, "this service")}</strong>
            {"? This action cannot be undone."}
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={isSameServiceId(
          deletingServiceUuid,
          serviceToDelete?.serviceId,
        )}
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
            <strong>{serviceLabel(confirmPublishService, "this service")}</strong>
            {"? The service will be available for use."}
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="green"
        isConfirmLoading={isSameServiceId(
          publishingServiceUuid,
          confirmPublishService?.serviceId,
        )}
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
              {serviceLabel(confirmUnpublishService, "this service")}
            </strong>
            {"? The service will no longer be available for use."}
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={isSameServiceId(
          unpublishingServiceUuid,
          confirmUnpublishService?.serviceId,
        )}
        confirmLoadingText="Unpublishing..."
        leastDestructiveRef={cancelUnpublishRef}
      />
    </>
  );
};

export default ServicesManagement;
