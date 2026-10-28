import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  HStack,
  Icon,
  Text,
  VStack,
} from "@chakra-ui/react";
import { EditIcon } from "@chakra-ui/icons";
import { FiEdit2, FiRefreshCw, FiSliders } from "react-icons/fi";
import { LuSplit } from "react-icons/lu";
import DataTable, {
  createActionsColumn,
  DEFAULT_PAGE_SIZE_OPTIONS,
  FieldLabel,
  type DataTableColumn,
} from "../common/table";
import CreateButton from "../common/CreateButton";
import FormActions from "../common/FormActions";
import FormDrawer from "../common/FormDrawer";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import ApplicationBudgetModal from "./ApplicationBudgetModal";
import ApplicationBulkBudgetModal from "./ApplicationBulkBudgetModal";
import ApplicationCreatedDialog from "./ApplicationCreatedDialog";
import ServiceFallbacksModal from "./ServiceFallbacksModal";
import ServiceFallbacksSummary from "./ServiceFallbacksSummary";
import ApplicationIdentityFields from "./ApplicationIdentityFields";
import FieldHint from "../common/FieldHint";
import PercentageStepper from "../common/PercentageStepper";
import { FIELD_HINTS } from "../../config/fieldHints";
import { APPLICATION_BUDGET_MANAGED_NOTE, BUDGET_COPY, editBudgetForName, percentageBoundMessage } from "../../config/budgetMessages";
import { SERVICE_FALLBACK_COPY } from "../../config/serviceFallbackMessages";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import type { Application } from "../../types/application";
import {
  ApplicationEmptyState,
  ApplicationIdentity,
  ApplicationLoadError,
  ApplicationNoResults,
  ApplicationStatusText,
  InstitutionAllocationPanel,
  InstitutionAllocationSkeleton,
} from "./applicationSurface";
import { useApplicationManagement } from "./hooks/useApplicationManagement";
import { useFallbackCatalogue, useServiceFallbackEditor } from "./hooks/useServiceFallbacks";
import { useDeferredColumnSort } from "../../utils/tableSort";

function formatPct(value: number | null | undefined): string {
  if (value == null) return "No ceiling";
  const rounded = Math.round(value * 100) / 100;
  if (rounded % 1 === 0) return `${rounded.toFixed(0)}%`;
  return `${rounded.toFixed(2)}%`;
}

function rupees(amount: number | null | undefined, currency: string): string {
  if (amount == null) return "—";
  return formatSpendMoney(amount, currency);
}

const FALLBACK_ACTION = SERVICE_FALLBACK_COPY.action;

function FallbackActionTooltip({ count }: Readonly<{ count: number }>) {
  return (
    <Box py={0.5}>
      <Text fontSize="xs" fontWeight="700" color="inherit">
        {FALLBACK_ACTION.label}
      </Text>
      <Text fontSize="xs" color="inherit">
        {count > 0 ? FALLBACK_ACTION.configured(count) : FALLBACK_ACTION.notConfigured}
      </Text>
    </Box>
  );
}

function applicationDrawerTitle(options: {
  isEditing: boolean;
  isCreating: boolean;
  formName: string;
  selectedName?: string;
  viewName?: string;
}): string {
  if (options.isEditing) {
    return options.formName || options.selectedName || "Edit Application";
  }
  if (options.isCreating) return "Create Application";
  return options.viewName || "Application";
}

function applicationDrawerDescription(options: {
  isEditing: boolean;
  isCreating: boolean;
  selectedName?: string;
}): string {
  if (options.isEditing) {
    if (options.selectedName) {
      return `Update details for ${options.selectedName}.`;
    }
    return "Update the application details.";
  }
  if (options.isCreating) {
    return "Add an application and set how much of the institution budget it can use.";
  }
  return "Application details.";
}

function ApplicationTableEmpty({
  hasSearch,
  onClearSearch,
  onCreate,
}: Readonly<{
  hasSearch: boolean;
  onClearSearch: () => void;
  onCreate: () => void;
}>) {
  if (hasSearch) {
    return <ApplicationNoResults onClear={onClearSearch} />;
  }
  return <ApplicationEmptyState onCreate={onCreate} />;
}

const HIDE_KEYS_COL = { display: { base: "none", lg: "table-cell" } } as const;

type ApplicationMgr = ReturnType<typeof useApplicationManagement>;
type FallbackCatalogueState = ReturnType<typeof useFallbackCatalogue>;

function createBudgetPreviewAmount(
  allocatedPercentage: string,
  tenantBudget: number,
): number | null {
  const pct = Number(allocatedPercentage);
  if (allocatedPercentage.trim() === "" || !Number.isFinite(pct)) return null;
  return (pct / 100) * tenantBudget;
}

function closeApplicationDrawer(
  mgr: ApplicationMgr,
  isEditing: boolean,
  isCreating: boolean,
): void {
  if ((isEditing || isCreating) && mgr.isSaving) return;
  if (isEditing) {
    mgr.setEditOpen(false);
    return;
  }
  if (isCreating) {
    mgr.setCreateOpen(false);
    return;
  }
  mgr.setViewOpen(false);
}

function ApplicationDrawerEditBody({
  mgr,
}: Readonly<{ mgr: ApplicationMgr }>) {
  return (
    <>
      <ApplicationIdentityFields
        mode="edit"
        form={mgr.form}
        setForm={mgr.setForm}
        errors={mgr.formErrors}
        banner={mgr.formBanner}
      />
      <Text fontSize="sm" color="ink.500" mt={4}>
        {APPLICATION_BUDGET_MANAGED_NOTE}
      </Text>
    </>
  );
}

function ApplicationDrawerCreateBody({
  mgr,
  currency,
  boundHint,
  setBoundHint,
}: Readonly<{
  mgr: ApplicationMgr;
  currency: string;
  boundHint: string | null;
  setBoundHint: (hint: string | null) => void;
}>) {
  const createPreview = createBudgetPreviewAmount(
    mgr.form.allocated_percentage,
    mgr.tenantBudget,
  );
  const createBudgetError = mgr.formErrors.allocated_percentage || boundHint;
  const createPreviewHint =
    createPreview == null
      ? ""
      : ` · ≈ ${formatSpendMoney(createPreview, currency)}`;

  return (
    <>
      <ApplicationIdentityFields
        mode="create"
        form={mgr.form}
        setForm={mgr.setForm}
        errors={mgr.formErrors}
        banner={mgr.formBanner}
      />
      <FormSection title="Budget">
        <FormControl isInvalid={Boolean(createBudgetError)}>
          <FieldLabel hint={FIELD_HINTS.application.budget.tip}>
            Budget allocation
          </FieldLabel>
          <PercentageStepper
            value={mgr.form.allocated_percentage}
            onChange={(next) => {
              setBoundHint(null);
              mgr.setForm((prev) => ({ ...prev, allocated_percentage: next }));
            }}
            onBoundHit={(bound) => setBoundHint(percentageBoundMessage(bound))}
          />
          <FormErrorMessage>{createBudgetError}</FormErrorMessage>
          <FieldHint show={createBudgetError == null}>
            {mgr.remainingPct.toFixed(2)}% remaining
            {createPreviewHint}
          </FieldHint>
        </FormControl>
      </FormSection>
    </>
  );
}

function ApplicationDrawerViewBody({
  viewApp,
  currency,
  fallbackCatalogue,
  onConfigureFallbacks,
}: Readonly<{
  viewApp: Application;
  currency: string;
  fallbackCatalogue: FallbackCatalogueState;
  onConfigureFallbacks: (app: Application) => void;
}>) {
  const allocationExtra =
    viewApp.allocated_budget == null
      ? ""
      : ` · ${rupees(viewApp.allocated_budget, currency)}`;
  const keyCount =
    viewApp.api_key_count == null ? "—" : String(viewApp.api_key_count);

  return (
    <>
      <ApplicationIdentityFields
        mode="view"
        form={{
          name: viewApp.name,
          description: viewApp.description ?? "",
          domain: viewApp.domain ?? "",
          allocated_percentage: "",
        }}
        setForm={() => undefined}
        errors={{}}
        banner={null}
      />
      <FormSection title="Budget">
        <ReadOnlyField label="Status">
          <ApplicationStatusText status={viewApp.status} />
        </ReadOnlyField>
        <ReadOnlyField label="Allocation">
          {formatPct(viewApp.allocated_percentage)}
          {allocationExtra}
        </ReadOnlyField>
        <ReadOnlyField label="Active API keys">{keyCount}</ReadOnlyField>
      </FormSection>
      <ServiceFallbacksSummary
        fallbacks={viewApp.service_fallbacks}
        catalogue={fallbackCatalogue.catalogue}
        isLoading={fallbackCatalogue.status === "loading"}
        onConfigure={() => onConfigureFallbacks(viewApp)}
      />
    </>
  );
}

function ApplicationDrawerFooter({
  isEditing,
  isCreating,
  isSaving,
  onClose,
  onSubmit,
}: Readonly<{
  isEditing: boolean;
  isCreating: boolean;
  isSaving: boolean;
  onClose: () => void;
  onSubmit: () => void;
}>) {
  if (isEditing || isCreating) {
    return (
      <FormActions
        cancelLabel="Cancel"
        submitLabel={isEditing ? "Save Changes" : "Create Application"}
        onCancel={onClose}
        onSubmit={onSubmit}
        isLoading={isSaving}
        loadingText={isEditing ? "Saving..." : "Creating..."}
        justify="space-between"
        pt={0}
      />
    );
  }
  return <FormActions hideSubmit cancelLabel="Close" onCancel={onClose} pt={0} />;
}

function ApplicationFormDrawer({
  mgr,
  currency,
  boundHint,
  setBoundHint,
  fallbackCatalogue,
  onConfigureFallbacks,
}: Readonly<{
  mgr: ApplicationMgr;
  currency: string;
  boundHint: string | null;
  setBoundHint: (hint: string | null) => void;
  fallbackCatalogue: FallbackCatalogueState;
  onConfigureFallbacks: (app: Application) => void;
}>) {
  const isEditing = mgr.editOpen;
  const isCreating = mgr.createOpen;
  const viewApp = mgr.viewOpen ? mgr.selected : null;
  const isViewing = Boolean(viewApp) && !isEditing && !isCreating;
  const closeDrawer = () => closeApplicationDrawer(mgr, isEditing, isCreating);

  return (
    <FormDrawer
      isOpen={isEditing || isCreating || Boolean(viewApp)}
      onClose={closeDrawer}
      lockDismiss={(isEditing || isCreating) && mgr.isSaving}
      actions={
        isViewing && viewApp ? (
          <Button
            leftIcon={<FiEdit2 />}
            size="sm"
            variant="outline"
            onClick={() => mgr.openEdit(viewApp)}
          >
            Edit
          </Button>
        ) : undefined
      }
      title={applicationDrawerTitle({
        isEditing,
        isCreating,
        formName: mgr.form.name,
        selectedName: mgr.selected?.name,
        viewName: viewApp?.name,
      })}
      description={applicationDrawerDescription({
        isEditing,
        isCreating,
        selectedName: mgr.selected?.name,
      })}
      footer={
        <ApplicationDrawerFooter
          isEditing={isEditing}
          isCreating={isCreating}
          isSaving={mgr.isSaving}
          onClose={closeDrawer}
          onSubmit={() => void (isEditing ? mgr.handleEdit() : mgr.handleCreate())}
        />
      }
    >
      {isEditing ? <ApplicationDrawerEditBody mgr={mgr} /> : null}
      {isCreating ? (
        <ApplicationDrawerCreateBody
          mgr={mgr}
          currency={currency}
          boundHint={boundHint}
          setBoundHint={setBoundHint}
        />
      ) : null}
      {isViewing && viewApp ? (
        <ApplicationDrawerViewBody
          viewApp={viewApp}
          currency={currency}
          fallbackCatalogue={fallbackCatalogue}
          onConfigureFallbacks={onConfigureFallbacks}
        />
      ) : null}
    </FormDrawer>
  );
}

function ApplicationListPanel({
  mgr,
  currency,
  columns,
  sortedApplications,
  appSort,
}: Readonly<{
  mgr: ApplicationMgr;
  currency: string;
  columns: DataTableColumn<Application>[];
  sortedApplications: Application[];
  appSort: ReturnType<typeof useDeferredColumnSort>;
}>) {
  const summaryPending =
    mgr.isLoading && mgr.applications.length === 0 && !mgr.loadError;
  const hasSearch = mgr.searchInput.trim() !== "";
  const showPartialLoadError = Boolean(mgr.loadError && mgr.applications.length > 0);
  const showFullLoadError = Boolean(mgr.loadError && mgr.applications.length === 0);

  return (
    <VStack align="stretch" spacing={4}>
      <HStack justify="space-between" align="flex-start" spacing={4} flexWrap="wrap">
        <Box minW={0}>
          <Text as="h2" fontSize="xl" fontWeight="700" color="ink.800" letterSpacing="-0.02em">
            Applications
          </Text>
          <Text fontSize="sm" color="ink.500" mt={1} maxW="520px">
            Manage applications onboarded under this institution and their budget allocation.
          </Text>
        </Box>
        <HStack spacing={2} flexShrink={0} flexWrap="wrap" justify="flex-end">
          <Button
            leftIcon={<FiRefreshCw />}
            size="sm"
            variant="ghost"
            onClick={() => void mgr.reload()}
          >
            Refresh
          </Button>
          <Button
            leftIcon={<FiSliders />}
            size="sm"
            variant="outline"
            onClick={() => void mgr.openBulkBudget()}
          >
            {BUDGET_COPY.bulkUpdateBudgets}
          </Button>
          <CreateButton onClick={mgr.openCreate}>Create Application</CreateButton>
        </HStack>
      </HStack>

      {summaryPending ? (
        <InstitutionAllocationSkeleton />
      ) : (
        <InstitutionAllocationPanel
          applicationCount={mgr.institutionApplicationCount ?? mgr.total}
          allocatedPct={mgr.totalAllocatedPct}
          availablePct={mgr.remainingPct}
          institutionBudget={mgr.tenantBudget}
          currency={currency}
          overAllocated={mgr.totalAllocatedPct > 100 + 1e-6}
        />
      )}

      {mgr.institutionBudgetUnset && !summaryPending ? (
        <Alert status="warning" borderRadius="md">
          <AlertIcon />
          {FIELD_HINTS.application.institutionBudgetNotSet}
        </Alert>
      ) : null}

      {showPartialLoadError ? (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          Unable to load applications. Please try again.
          <Button size="xs" variant="outline" colorScheme="red" ml={3} onClick={() => void mgr.reload()}>
            Retry
          </Button>
        </Alert>
      ) : null}

      {showFullLoadError ? (
        <ApplicationLoadError onRetry={() => void mgr.reload()} />
      ) : (
        <DataTable
          layout="admin"
          toolbarAttached
          items={sortedApplications}
          columns={columns}
          getRowKey={(app) => app.application_id}
          sort={appSort.sort}
          onSortChange={appSort.onSortChange}
          onRowClick={mgr.openView}
          paginate="server"
          paginationPosition="bottom"
          pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
          initialPageSize={mgr.pageSize}
          serverPagination={{
            page: mgr.page,
            pageSize: mgr.pageSize,
            totalItems: mgr.total,
            onPageChange: mgr.setPage,
            onPageSizeChange: mgr.setPageSize,
          }}
          isLoading={mgr.isLoading && mgr.applications.length === 0 && !mgr.loadError}
          emptyContent={
            <ApplicationTableEmpty
              hasSearch={hasSearch}
              onClearSearch={() => mgr.setSearchInput("")}
              onCreate={mgr.openCreate}
            />
          }
          emptyMessage="No applications yet."
          noResultsMessage="No applications match this search."
          unfilteredCount={mgr.total}
          hasActiveFilters={hasSearch}
          onClearFilters={() => mgr.setSearchInput("")}
          search={{
            label: "Search applications",
            hideLabel: true,
            value: mgr.searchInput,
            onChange: mgr.setSearchInput,
            placeholder: "Search applications...",
            fields: ["name", "domain"],
          }}
        />
      )}

      <ApplicationBudgetModal mgr={mgr} currency={currency} />

      <ApplicationBulkBudgetModal
        isOpen={mgr.bulkBudgetOpen}
        onClose={() => mgr.setBulkBudgetOpen(false)}
        isLoading={mgr.bulkLoading}
        isSaving={mgr.isSaving}
        banner={mgr.bulkBanner}
        tenantBudget={mgr.tenantBudget}
        institutionBudgetUnset={mgr.institutionBudgetUnset}
        currency={currency}
        liveTotalPct={mgr.bulkLiveTotalPct}
        rows={mgr.bulkRows}
        onRowFocus={mgr.onBulkRowFocus}
        onPctChange={mgr.onBulkPctChange}
        onPctBoundHit={mgr.onBulkPctBoundHit}
        onSave={() => void mgr.handleSaveBulkBudget()}
        canSave={mgr.bulkCanSave}
      />
    </VStack>
  );
}

function buildApplicationColumns(options: {
  currency: string;
  onEdit: (app: Application) => void;
  onBudget: (app: Application) => void;
  onFallbacks: (app: Application) => void;
}): DataTableColumn<Application>[] {
  return [
    {
      id: "name",
      header: "Application",
      sortable: true,
      sortAccessor: (app) => app.name ?? "",
      truncate: false,
      cell: (app) => (
        <ApplicationIdentity name={app.name} description={app.description} />
      ),
    },
    {
      id: "domain",
      header: "Domain",
      hint: FIELD_HINTS.application.col.domain,
      sortable: true,
      sortAccessor: (app) => app.domain ?? "",
      cell: (app) => (
        <Text fontSize="sm" color={app.domain ? "ink.700" : "ink.400"}>
          {app.domain || "—"}
        </Text>
      ),
    },
    {
      id: "budget",
      header: "Budget",
      hint: FIELD_HINTS.application.col.budget,
      sortable: true,
      sortAccessor: (app) => app.allocated_percentage ?? -1,
      truncate: false,
      cell: (app) => (
        <Box>
          <Text fontSize="md" fontWeight="700" color="ink.800" letterSpacing="-0.02em">
            {formatPct(app.allocated_percentage)}
          </Text>
          {typeof app.allocated_budget === "number" ? (
            <Text fontSize="xs" color="ink.500">
              {rupees(app.allocated_budget, options.currency)}
            </Text>
          ) : null}
        </Box>
      ),
    },
    {
      id: "keys",
      header: "Active API keys",
      hint: FIELD_HINTS.application.col.keys,
      sortable: true,
      sortAccessor: (app) => app.api_key_count ?? -1,
      thProps: HIDE_KEYS_COL,
      tdProps: HIDE_KEYS_COL,
      cell: (app) => (
        <Text fontSize="sm" color="ink.700">
          {app.api_key_count == null ? "—" : String(app.api_key_count)}
        </Text>
      ),
    },
    {
      id: "status",
      header: "Status",
      hint: FIELD_HINTS.application.col.status,
      sortable: true,
      sortAccessor: (app) => app.status ?? "",
      truncate: false,
      cell: (app) => <ApplicationStatusText status={app.status} />,
    },
    createActionsColumn<Application>({
      actionCount: 3,
      getActions: (app) => {
        const budgetActionLabel = editBudgetForName(app.name);
        const budgetDisabled = app.status !== "ACTIVE";
        const fallbackCount = Object.keys(app.service_fallbacks).length;
        return [
          {
            id: "edit",
            label: "Edit",
            icon: <EditIcon />,
            "aria-label": `Edit ${app.name}`,
            onClick: () => options.onEdit(app),
          },
          {
            id: "budget",
            label: "Edit budget",
            icon: <Icon as={FiSliders} />,
            tooltip: budgetDisabled
              ? FIELD_HINTS.application.inactiveBudgetNotEditable
              : budgetActionLabel,
            "aria-label": budgetDisabled
              ? FIELD_HINTS.application.inactiveBudgetNotEditable
              : budgetActionLabel,
            disabled: budgetDisabled,
            onClick: () => options.onBudget(app),
          },
          {
            id: "fallbacks",
            label: FALLBACK_ACTION.label,
            icon: <Icon as={LuSplit} />,
            tooltip: <FallbackActionTooltip count={fallbackCount} />,
            "aria-label": `${FALLBACK_ACTION.label} for ${app.name}`,
            color: fallbackCount > 0 ? "teal.600" : undefined,
            hoverColor: "teal.700",
            hoverBg: "teal.50",
            onClick: () => options.onFallbacks(app),
          },
        ];
      },
    }),
  ];
}

export default function ApplicationManagementTab({
  tenantId,
  institutionBudget,
  currency = "INR",
}: Readonly<{
  tenantId: string;
  institutionBudget: number | null;
  currency?: string;
}>) {
  const mgr = useApplicationManagement(tenantId, institutionBudget, currency);
  const [boundHint, setBoundHint] = useState<string | null>(null);
  const [fallbacksOpen, setFallbacksOpen] = useState(false);
  /** Reopen the details drawer when the editor was opened from it. */
  const [fallbacksFromView, setFallbacksFromView] = useState(false);

  // Loaded for the details view and the editor; the created prompt warms it up.
  const fallbackCatalogue = useFallbackCatalogue(
    tenantId,
    mgr.viewOpen || fallbacksOpen || mgr.createdApplication != null,
  );
  const fallbackEditor = useServiceFallbackEditor({
    tenantId,
    catalogue: fallbackCatalogue.catalogue,
    catalogueReady: fallbackCatalogue.status === "ready",
    onSaved: () => {
      mgr.reload();
    },
    onClose: (app) => {
      setFallbacksOpen(false);
      if (fallbacksFromView) mgr.openView(app);
      setFallbacksFromView(false);
    },
  });
  const openFallbackEditor = fallbackEditor.open;
  const { setViewOpen } = mgr;
  const openFallbacks = useCallback(
    (app: Application, fromView: boolean) => {
      setFallbacksFromView(fromView);
      setFallbacksOpen(true);
      if (fromView) setViewOpen(false);
      openFallbackEditor(app);
    },
    [openFallbackEditor, setViewOpen],
  );

  useEffect(() => {
    if (!mgr.createOpen) setBoundHint(null);
  }, [mgr.createOpen]);

  const appSortAccessors = useMemo(
    () => ({
      name: (app: Application) => app.name ?? "",
      domain: (app: Application) => app.domain ?? "",
      budget: (app: Application) => app.allocated_percentage ?? -1,
      keys: (app: Application) => app.api_key_count ?? -1,
      status: (app: Application) => app.status ?? "",
    }),
    [],
  );
  const appSort = useDeferredColumnSort("name", appSortAccessors);
  const sortedApplications = useMemo(
    () => appSort.apply(mgr.applications),
    [mgr.applications, appSort],
  );

  const columns = useMemo(
    () =>
      buildApplicationColumns({
        currency,
        onEdit: mgr.openEdit,
        onBudget: mgr.openBudget,
        onFallbacks: (app) => openFallbacks(app, false),
      }),
    [currency, mgr.openEdit, mgr.openBudget, openFallbacks],
  );

  if (!tenantId) {
    return (
      <Alert status="warning" borderRadius="md">
        <AlertIcon />
        Your Institution could not be resolved, so Applications cannot be loaded.
      </Alert>
    );
  }

  return (
    <>
      <ApplicationFormDrawer
        mgr={mgr}
        currency={currency}
        boundHint={boundHint}
        setBoundHint={setBoundHint}
        fallbackCatalogue={fallbackCatalogue}
        onConfigureFallbacks={(app) => openFallbacks(app, true)}
      />
      <ApplicationListPanel
        mgr={mgr}
        currency={currency}
        columns={columns}
        sortedApplications={sortedApplications}
        appSort={appSort}
      />
      <ApplicationCreatedDialog
        application={mgr.createdApplication}
        onSkip={mgr.dismissCreatedPrompt}
        onConfigure={(app) => {
          mgr.dismissCreatedPrompt();
          openFallbacks(app, false);
        }}
      />
      <ServiceFallbacksModal editor={fallbackEditor} catalogueState={fallbackCatalogue} />
    </>
  );
}
