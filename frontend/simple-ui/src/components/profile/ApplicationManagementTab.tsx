import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  HStack,
  Text,
  VStack,
} from "@chakra-ui/react";
import { FiEdit2, FiRefreshCw, FiSliders } from "react-icons/fi";
import DataTable, {
  DataTableActions,
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
import ApplicationIdentityFields from "./ApplicationIdentityFields";
import FieldHint from "../common/FieldHint";
import PercentageStepper from "../common/PercentageStepper";
import { FIELD_HINTS } from "../../config/fieldHints";
import { BUDGET_COPY, percentageBoundMessage } from "../../config/budgetMessages";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import type { Application } from "../../types/application";
import {
  ApplicationEmptyState,
  ApplicationIdentity,
  ApplicationListSkeleton,
  ApplicationLoadError,
  ApplicationNoResults,
  ApplicationStatusText,
  InstitutionAllocationPanel,
  InstitutionAllocationSkeleton,
} from "./applicationSurface";
import { useApplicationManagement } from "./hooks/useApplicationManagement";
import { useDeferredColumnSort } from "../../utils/tableSort";

function formatPct(value: number | null | undefined): string {
  if (value == null) return "No ceiling";
  const rounded = Math.round(value * 100) / 100;
  return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(2)}%`;
}

function rupees(amount: number | null | undefined, currency: string): string {
  if (amount == null) return "—";
  return formatSpendMoney(amount, currency);
}

export default function ApplicationManagementTab({
  tenantId,
  institutionBudget,
  currency = "INR",
}: {
  tenantId: string;
  institutionBudget: number | null;
  currency?: string;
}) {
  const mgr = useApplicationManagement(tenantId, institutionBudget, currency);
  const [boundHint, setBoundHint] = useState<string | null>(null);

  useEffect(() => {
    if (!mgr.createOpen) setBoundHint(null);
  }, [mgr.createOpen]);

  const appSortAccessors = useMemo(
    () => ({
      name: (app: Application) => app.name ?? "",
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

  const hideKeys = { display: { base: "none", lg: "table-cell" } } as const;
  const columns: DataTableColumn<Application>[] = [
    {
      id: "name",
      header: "Application",
      sortable: true,
      sortAccessor: (app) => app.name ?? "",
      truncate: false,
      cell: (app) => (
        <ApplicationIdentity
          name={app.name}
          description={app.description}
          domain={app.domain}
        />
      ),
    },
    {
      id: "budget",
      header: "Budget",
      sortable: true,
      sortAccessor: (app) => app.allocated_percentage ?? -1,
      truncate: false,
      cell: (app) => (
        <Box>
          <Text fontSize="md" fontWeight="700" color="ink.800" letterSpacing="-0.02em">
            {formatPct(app.allocated_percentage)}
          </Text>
          {app.allocated_budget != null ? (
            <Text fontSize="xs" color="ink.500">
              {rupees(app.allocated_budget, currency)}
            </Text>
          ) : null}
        </Box>
      ),
    },
    {
      id: "keys",
      header: "API keys",
      sortable: true,
      sortAccessor: (app) => app.api_key_count ?? -1,
      thProps: hideKeys,
      tdProps: hideKeys,
      cell: (app) => (
        <Text fontSize="sm" color="ink.700">
          {app.api_key_count == null
            ? "—"
            : `${app.api_key_count} ${app.api_key_count === 1 ? "key" : "keys"}`}
        </Text>
      ),
    },
    {
      id: "status",
      header: "Status",
      sortable: true,
      sortAccessor: (app) => app.status ?? "",
      truncate: false,
      cell: (app) => <ApplicationStatusText status={app.status} />,
    },
    {
      id: "actions",
      header: "",
      align: "right",
      truncate: false,
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (app) => (
        <DataTableActions
          justify="flex-end"
          actions={[
            {
              id: "view",
              label: `View ${app.name}`,
              onClick: () => mgr.openView(app),
            },
            {
              id: "edit",
              label: `Edit ${app.name}`,
              onClick: () => mgr.openEdit(app),
            },
            {
              id: "budget",
              label: `Edit budget for ${app.name}`,
              icon: <FiSliders />,
              tooltip:
                app.status === "ACTIVE"
                  ? `Edit budget for ${app.name}`
                  : FIELD_HINTS.application.inactiveBudgetNotEditable,
              "aria-label":
                app.status === "ACTIVE"
                  ? `Edit budget for ${app.name}`
                  : FIELD_HINTS.application.inactiveBudgetNotEditable,
              disabled: app.status !== "ACTIVE",
              onClick: () => mgr.openBudget(app),
            },
          ]}
        />
      ),
    },
  ];

  if (!tenantId) {
    return (
      <Alert status="warning" borderRadius="md">
        <AlertIcon />
        Your Institution could not be resolved, so Applications cannot be loaded.
      </Alert>
    );
  }

  const createPct = Number(mgr.form.allocated_percentage);
  const createPreview =
    mgr.form.allocated_percentage.trim() === "" || !Number.isFinite(createPct)
      ? null
      : (createPct / 100) * mgr.tenantBudget;
  const createBudgetError = mgr.formErrors.allocated_percentage || boundHint;
  const summaryPending = mgr.isLoading && mgr.applications.length === 0 && !mgr.loadError;

  const isEditing = mgr.editOpen;
  const isCreating = mgr.createOpen;
  const viewApp = mgr.viewOpen ? mgr.selected : null;
  const closeDrawer = () => {
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
  };

  return (
    <>
      <FormDrawer
        isOpen={isEditing || isCreating || Boolean(viewApp)}
        onClose={closeDrawer}
        title={
          isEditing
            ? mgr.form.name || mgr.selected?.name || "Edit Application"
            : isCreating
              ? "Create Application"
              : viewApp?.name || "Application"
        }
        description={
          isEditing
            ? mgr.selected
              ? `Update details for ${mgr.selected.name}.`
              : "Update the application details."
            : isCreating
              ? "Add an application and set how much of the institution budget it can use."
              : "Application details."
        }
        footer={
          isEditing ? (
            <FormActions
              cancelLabel="Cancel"
              submitLabel="Save Changes"
              onCancel={closeDrawer}
              onSubmit={() => void mgr.handleEdit()}
              isLoading={mgr.isSaving}
              loadingText="Saving..."
              justify="flex-end"
              pt={0}
            />
          ) : isCreating ? (
            <FormActions
              cancelLabel="Cancel"
              submitLabel="Create Application"
              onCancel={closeDrawer}
              onSubmit={() => void mgr.handleCreate()}
              isLoading={mgr.isSaving}
              loadingText="Creating..."
              justify="flex-end"
              pt={0}
            />
          ) : (
            <FormActions hideSubmit cancelLabel="Back" onCancel={closeDrawer} pt={0} />
          )
        }
      >
        {isEditing ? (
          <>
            <ApplicationIdentityFields
              mode="edit"
              form={mgr.form}
              setForm={mgr.setForm}
              errors={mgr.formErrors}
              banner={mgr.formBanner}
            />
            <Text fontSize="sm" color="ink.500" mt={4}>
              Budget is managed separately — use Edit Budget on the application row.
            </Text>
          </>
        ) : isCreating ? (
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
                <FieldLabel>Budget allocation</FieldLabel>
                <PercentageStepper
                  value={mgr.form.allocated_percentage}
                  onChange={(next) => {
                    setBoundHint(null);
                    mgr.setForm((prev) => ({ ...prev, allocated_percentage: next }));
                  }}
                  onBoundHit={(bound) => setBoundHint(percentageBoundMessage(bound))}
                />
                <FormErrorMessage>{createBudgetError}</FormErrorMessage>
                <FieldHint show={!createBudgetError}>
                  {FIELD_HINTS.application.budget.helper} {mgr.remainingPct.toFixed(2)}% remaining.
                  {createPreview != null ? ` ≈ ${formatSpendMoney(createPreview, currency)}` : ""}
                </FieldHint>
              </FormControl>
            </FormSection>
          </>
        ) : viewApp ? (
          <>
            <Button
              leftIcon={<FiEdit2 />}
              size="sm"
              variant="outline"
              mb={4}
              onClick={() => mgr.openEdit(viewApp)}
            >
              Edit application
            </Button>
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
                {viewApp.allocated_budget != null
                  ? ` · ${rupees(viewApp.allocated_budget, currency)}`
                  : ""}
              </ReadOnlyField>
              <ReadOnlyField label="API keys">
                {viewApp.api_key_count == null ? "—" : String(viewApp.api_key_count)}
              </ReadOnlyField>
            </FormSection>
          </>
        ) : null}
      </FormDrawer>
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

      {mgr.loadError && mgr.applications.length > 0 ? (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          Unable to load applications. Please try again.
          <Button size="xs" variant="outline" colorScheme="red" ml={3} onClick={() => void mgr.reload()}>
            Retry
          </Button>
        </Alert>
      ) : null}

      {mgr.loadError && mgr.applications.length === 0 ? (
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
        showRowChevron={false}
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
        loadingContent={<ApplicationListSkeleton />}
        emptyContent={
          mgr.searchInput.trim() ? (
            <ApplicationNoResults onClear={() => mgr.setSearchInput("")} />
          ) : (
            <ApplicationEmptyState onCreate={mgr.openCreate} />
          )
        }
        emptyMessage="No applications yet."
        noResultsMessage="No applications match this search."
        unfilteredCount={mgr.total}
        hasActiveFilters={mgr.searchInput.trim() !== ""}
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
    </>
  );
}
