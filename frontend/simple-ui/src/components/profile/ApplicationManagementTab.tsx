import React, { useMemo } from "react";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  FormControl,
  FormErrorMessage,
  HStack,
  IconButton,
  Input,
  SimpleGrid,
  Text,
  Textarea,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { EditIcon } from "@chakra-ui/icons";
import { FiRefreshCw, FiSliders } from "react-icons/fi";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  FieldLabel,
  type DataTableColumn,
} from "../common/table";
import StandardModal, { CreateModal } from "../common/StandardModal";
import CreateButton from "../common/CreateButton";
import FormActions from "../common/FormActions";
import ApplicationBulkBudgetModal from "./ApplicationBulkBudgetModal";
import FieldHint from "../common/FieldHint";
import PercentageStepper from "../common/PercentageStepper";
import { FIELD_HINTS } from "../../config/fieldHints";
import { percentageBoundMessage } from "../../config/budgetMessages";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import type { Application } from "../../types/application";
import {
  useApplicationManagement,
  type ApplicationForm,
} from "./hooks/useApplicationManagement";
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

function ApplicationSummaryCard({
  label,
  tooltip,
  value,
  subValue,
}: {
  label: string;
  tooltip: string;
  value: string;
  subValue?: string;
}) {
  return (
    <Card bg="ink.50" borderColor="ink.200" borderWidth="1px" boxShadow="none">
      <CardBody py={4} px={5}>
        <Box mb={2}>
          <FieldLabel variant="metric" hint={tooltip}>
            {label}
          </FieldLabel>
        </Box>
        <Text fontSize="23px" fontWeight="800" letterSpacing="-0.4px">
          {value}
        </Text>
        {subValue ? (
          <Text fontSize="12px" color="ink.500" mt={1}>
            {subValue}
          </Text>
        ) : null}
      </CardBody>
    </Card>
  );
}

function ViewLabelWithTip({ label, tooltip }: { label: string; tooltip: string }) {
  return <FieldLabel variant="inline" hint={tooltip}>{label}</FieldLabel>;
}

const AVATAR_COLORS = [
  ["#7C5CFC", "#5B3EDB"],
  ["#2F9E44", "#1F7A31"],
  ["#E8590C", "#C44700"],
  ["#D6336C", "#A82255"],
];

function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase() || "AP";
}

function avatarGradient(name: string): string {
  let sum = 0;
  for (let i = 0; i < name.length; i += 1) sum += name.charCodeAt(i);
  const [from, to] = AVATAR_COLORS[sum % AVATAR_COLORS.length];
  return `linear-gradient(135deg, ${from}, ${to})`;
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
  const mgr = useApplicationManagement(tenantId, institutionBudget);

  const appSortAccessors = useMemo(
    () => ({
      name: (app: Application) => app.name ?? "",
      domain: (app: Application) => app.domain ?? "",
      budget: (app: Application) => app.allocated_percentage ?? -1,
      status: (app: Application) => app.status ?? "",
    }),
    [],
  );
  const appSort = useDeferredColumnSort("name", appSortAccessors);
  const sortedApplications = useMemo(
    () => appSort.apply(mgr.applications),
    [mgr.applications, appSort],
  );

  const columns: DataTableColumn<Application>[] = [
    {
      id: "name",
      header: "Application",
      sortable: true,
      sortAccessor: (app) => app.name ?? "",
      cell: (app) => (
        <HStack spacing={3} align="center">
          <Box
            w="28px"
            h="28px"
            minW="28px"
            borderRadius="full"
            bgImage={avatarGradient(app.name)}
            color="white"
            fontSize="11px"
            fontWeight="700"
            display="flex"
            alignItems="center"
            justifyContent="center"
          >
            {initialsFromName(app.name)}
          </Box>
          <Box>
            <Text fontWeight="medium" fontSize="sm">
              {app.name}
            </Text>
            <Text fontSize="11px" color="ink.500" noOfLines={1}>
              {app.description || "No description"}
            </Text>
          </Box>
        </HStack>
      ),
    },
    {
      id: "domain",
      header: "Domain",
      sortable: true,
      sortAccessor: (app) => app.domain ?? "",
      cell: (app) => (
        <Badge
          variant="subtle"
          colorScheme="gray"
          borderWidth="1px"
          borderColor="ink.300"
          fontWeight="600"
          fontSize="11px"
          px={2}
          py="3px"
          borderRadius="6px"
          textTransform="none"
        >
          {app.domain || "—"}
        </Badge>
      ),
    },
    {
      id: "budget",
      header: "Budget",
      sortable: true,
      sortAccessor: (app) => app.allocated_percentage ?? -1,
      cell: (app) => (
        <Text fontWeight="700">{formatPct(app.allocated_percentage)}</Text>
      ),
    },
    {
      id: "status",
      header: "Status",
      sortable: true,
      sortAccessor: (app) => app.status ?? "",
      cell: (app) => (
        <Badge colorScheme={app.status === "ACTIVE" ? "green" : "gray"}>
          {app.status === "ACTIVE" ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    {
      id: "actions",
      header: "",
      tdProps: { onClick: (e) => e.stopPropagation() },
      cell: (app) => (
        <HStack spacing={0}>
          <Tooltip label="Edit">
            <IconButton
              aria-label={`Edit ${app.name}`}
              icon={<EditIcon />}
              size="sm"
              variant="ghost"
              colorScheme="blue"
              _hover={{ bg: "blue.50" }}
              onClick={() => mgr.openEdit(app)}
            />
          </Tooltip>
          <Tooltip
            label={
              app.status === "ACTIVE"
                ? "Edit Budget"
                : FIELD_HINTS.application.inactiveBudgetNotEditable
            }
            hasArrow
          >
            <Box as="span" display="inline-block">
              <IconButton
                aria-label={`Edit Budget for ${app.name}`}
                icon={<FiSliders />}
                size="sm"
                variant="ghost"
                colorScheme="blue"
                _hover={{ bg: "blue.50" }}
                onClick={() => mgr.openBudget(app)}
                isDisabled={app.status !== "ACTIVE"}
              />
            </Box>
          </Tooltip>
        </HStack>
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

  return (
    <VStack align="stretch" spacing={6}>
      <HStack justify="space-between" align="flex-start" spacing={4} flexWrap="wrap">
        <Text fontSize="13.5px" color="ink.600" maxW="540px" lineHeight="1.5">
          Applications onboarded under this Institution, and their Budget allocation.
        </Text>
        <HStack spacing={2.5} flexShrink={0}>
          <Button
            leftIcon={<FiRefreshCw />}
            size="sm"
            variant="outline"
            fontWeight="700"
            onClick={() => void mgr.reload()}
          >
            Refresh
          </Button>
          <Button
            leftIcon={<FiSliders />}
            size="sm"
            variant="outline"
            fontWeight="700"
            onClick={() => void mgr.openBulkBudget()}
          >
            Edit Budget
          </Button>
          <CreateButton onClick={mgr.openCreate}>Create Application</CreateButton>
        </HStack>
      </HStack>

      <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
        <ApplicationSummaryCard
          label="Total Applications"
          tooltip={FIELD_HINTS.application.tooltips.totalApplications}
          value={String(mgr.total)}
        />
        <ApplicationSummaryCard
          label="Allocated Budget"
          tooltip={FIELD_HINTS.application.tooltips.allocatedBudget}
          value={formatPct(mgr.totalAllocatedPct)}
          subValue={`${rupees((mgr.totalAllocatedPct / 100) * mgr.tenantBudget, currency)} of ${rupees(mgr.tenantBudget, currency)}`}
        />
        <ApplicationSummaryCard
          label="Available to Allocate"
          tooltip={FIELD_HINTS.application.tooltips.availableToAllocate}
          value={formatPct(mgr.remainingPct)}
          subValue={`${rupees((mgr.remainingPct / 100) * mgr.tenantBudget, currency)} not yet assigned`}
        />
      </SimpleGrid>

      {mgr.loadError && (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          {mgr.loadError}
        </Alert>
      )}

      <DataTable
        layout="admin"
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
        isLoading={mgr.isLoading}
        emptyMessage="No Applications onboarded yet."
        noResultsMessage="No Applications match your search."
        unfilteredCount={mgr.total}
        hasActiveFilters={mgr.searchInput.trim() !== ""}
        onClearFilters={() => mgr.setSearchInput("")}
        search={{
          label: "Application Name or Domain",
          value: mgr.searchInput,
          onChange: mgr.setSearchInput,
          placeholder: FIELD_HINTS.application.search.placeholder,
          helper: FIELD_HINTS.application.search.helper,
          fields: ["name", "domain"],
        }}
      />

      <CreateModal
        isOpen={mgr.createOpen}
        onClose={() => mgr.setCreateOpen(false)}
        title="Create Application"
        description="Add an application and set how much of the institution budget it can use."
        size="lg"
        footer={
          <FormActions
            submitLabel="Create Application"
            onCancel={() => mgr.setCreateOpen(false)}
            onSubmit={() => void mgr.handleCreate()}
            isLoading={mgr.isSaving}
            loadingText="Creating..."
            justify="space-between"
            pt={0}
          />
        }
      >
        <ApplicationIdentityFields
          mode="create"
          form={mgr.form}
          setForm={mgr.setForm}
          errors={mgr.formErrors}
          banner={mgr.formBanner}
          showBudget
          remainingPct={mgr.remainingPct}
          budgetPreview={createPreview}
          currency={currency}
        />
      </CreateModal>

      <StandardModal
        isOpen={mgr.editOpen}
        onClose={() => mgr.setEditOpen(false)}
        title="Edit Application"
        description={
          mgr.selected
            ? `Update details for ${mgr.selected.name}.`
            : "Update the application details."
        }
        size="lg"
        scrollBehavior="inside"
        modalProps={{ blockScrollOnMount: true }}
        headerProps={{ px: 6, pt: 5, pb: 4 }}
        bodyProps={{ px: 6, py: 5 }}
        footerProps={{ px: 6, py: 4 }}
        footer={
          <FormActions
            submitLabel="Save Changes"
            onCancel={() => mgr.setEditOpen(false)}
            onSubmit={() => void mgr.handleEdit()}
            isLoading={mgr.isSaving}
            loadingText="Saving..."
            justify="space-between"
            pt={0}
          />
        }
      >
        <ApplicationIdentityFields
          mode="edit"
          form={mgr.form}
          setForm={mgr.setForm}
          errors={mgr.formErrors}
          banner={mgr.formBanner}
          showBudget={false}
        />
      </StandardModal>

      <StandardModal
        isOpen={mgr.viewOpen}
        onClose={() => mgr.setViewOpen(false)}
        title="Application Details"
        description="View the application's information."
        size="lg"
        scrollBehavior="inside"
        modalProps={{ blockScrollOnMount: true }}
        headerProps={{ px: 6, pt: 5, pb: 4 }}
        bodyProps={{ px: 6, py: 5 }}
        footerProps={{ px: 6, py: 4 }}
        footer={
          mgr.selected ? (
            <FormActions
              cancelLabel="Close"
              submitLabel="Edit"
              onCancel={() => mgr.setViewOpen(false)}
              onSubmit={() => {
                mgr.setViewOpen(false);
                mgr.openEdit(mgr.selected!);
              }}
              justify="space-between"
              pt={0}
            />
          ) : (
            <FormActions
              submitLabel="Close"
              hideCancel
              onSubmit={() => mgr.setViewOpen(false)}
              pt={0}
            />
          )
        }
      >
        {mgr.selected && (
          <VStack align="stretch" spacing={4}>
            <HStack spacing={2}>
              <Badge colorScheme={mgr.selected.status === "ACTIVE" ? "green" : "gray"}>
                {mgr.selected.status === "ACTIVE" ? "Active" : "Inactive"}
              </Badge>
            </HStack>
            <ApplicationIdentityFields
              mode="view"
              form={{
                name: mgr.selected.name,
                description: mgr.selected.description ?? "",
                domain: mgr.selected.domain ?? "",
                allocated_percentage:
                  mgr.selected.allocated_percentage == null
                    ? ""
                    : String(mgr.selected.allocated_percentage),
              }}
              setForm={() => undefined}
              errors={{}}
              banner={null}
              showBudget
            />
            {mgr.selected.allocated_budget != null ? (
              <HStack justify="space-between">
                <FieldLabel variant="inline">Budget amount</FieldLabel>
                <Text fontWeight="semibold">
                  {rupees(mgr.selected.allocated_budget, currency)}
                </Text>
              </HStack>
            ) : null}
          </VStack>
        )}
      </StandardModal>

      <StandardModal
        isOpen={mgr.budgetOpen}
        onClose={() => mgr.setBudgetOpen(false)}
        title="Edit Budget"
        description={
          mgr.selected
            ? `Adjust how much of the institution budget ${mgr.selected.name} can use.`
            : "Adjust the application budget allocation."
        }
        size="lg"
        scrollBehavior="inside"
        modalProps={{ blockScrollOnMount: true }}
        headerProps={{ px: 6, pt: 5, pb: 4 }}
        bodyProps={{ px: 6, py: 5 }}
        footerProps={{ px: 6, py: 4 }}
        footer={
          <FormActions
            submitLabel="Save Changes"
            onCancel={() => mgr.setBudgetOpen(false)}
            onSubmit={() => void mgr.handleSaveBudget()}
            isLoading={mgr.isSaving}
            isDisabled={
              Boolean(mgr.budgetFieldError) ||
              mgr.institutionBudgetUnset ||
              mgr.selected?.status !== "ACTIVE"
            }
            loadingText="Saving..."
            justify="space-between"
            pt={0}
          />
        }
      >
        <VStack align="stretch" spacing={4}>
          <Box bg="blue.50" borderRadius="md" p={4}>
            <HStack justify="space-between" mb={2}>
              <FieldLabel
                variant="inline"
                hint={FIELD_HINTS.application.tooltips.institutionBudgetAllocated}
                textProps={{
                  fontSize: "xs",
                  fontWeight: "bold",
                  color: "ink.500",
                  textTransform: "uppercase",
                }}
              >
                Institution Budget allocated
              </FieldLabel>
              <Text fontWeight="bold">{formatPct(mgr.budgetLiveTotal)}</Text>
            </HStack>
            <Box h="8px" bg="ink.200" borderRadius="full" overflow="hidden">
              <Box
                h="100%"
                bg={mgr.budgetLiveTotal > 100 + 1e-6 ? "red.500" : "blue.500"}
                width={`${Math.min(mgr.budgetLiveTotal, 100)}%`}
              />
            </Box>
          </Box>
          {mgr.institutionBudgetUnset && (
            <Alert status="warning" borderRadius="md">
              <AlertIcon />
              {FIELD_HINTS.application.institutionBudgetNotSet}
            </Alert>
          )}
          {mgr.budgetBanner && (
            <Alert status="error" borderRadius="md">
              <AlertIcon />
              {mgr.budgetBanner}
            </Alert>
          )}
          {mgr.selected?.status !== "ACTIVE" && (
            <Alert status="info" borderRadius="md">
              <AlertIcon />
              {FIELD_HINTS.application.inactiveBudgetNotEditable}
            </Alert>
          )}
          <FormControl isInvalid={Boolean(mgr.budgetFieldError || mgr.budgetStepperHint)}>
            <FieldLabel>{mgr.selected ? `${mgr.selected.name}’s Budget` : "Budget"}</FieldLabel>
            <PercentageStepper
              value={mgr.budgetDraft}
              onChange={mgr.setBudgetDraft}
              onBoundHit={mgr.onBudgetBoundHit}
              isDisabled={mgr.selected?.status !== "ACTIVE"}
            />
            <FormErrorMessage>{mgr.budgetFieldError || mgr.budgetStepperHint}</FormErrorMessage>
            <FieldHint show={!mgr.budgetFieldError && !mgr.budgetStepperHint}>
              {FIELD_HINTS.application.budgetEdit.helper}
            </FieldHint>
          </FormControl>
          {mgr.budgetFloor > 0 ? (
            <HStack justify="space-between">
              <ViewLabelWithTip
                label="Minimum allowed"
                tooltip={FIELD_HINTS.application.tooltips.minimumAllowed}
              />
              <Text fontWeight="semibold">{formatPct(mgr.budgetFloor)}</Text>
            </HStack>
          ) : null}
          <HStack justify="space-between">
            <ViewLabelWithTip
              label="Available at Institution level"
              tooltip={FIELD_HINTS.application.tooltips.availableAtInstitution}
            />
            <Text fontWeight="semibold">{formatPct(mgr.budgetAvailable)}</Text>
          </HStack>
        </VStack>
      </StandardModal>

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

function ApplicationIdentityFields({
  mode,
  form,
  setForm,
  errors,
  banner,
  showBudget,
  remainingPct = 0,
  budgetPreview,
  currency = "INR",
}: {
  mode: "create" | "edit" | "view";
  form: ApplicationForm;
  setForm: React.Dispatch<React.SetStateAction<ApplicationForm>>;
  errors: Record<string, string>;
  banner: string | null;
  showBudget: boolean;
  remainingPct?: number;
  budgetPreview?: number | null;
  currency?: string;
}) {
  const isView = mode === "view";
  const [boundHint, setBoundHint] = React.useState<string | null>(null);
  const budgetError = errors.allocated_percentage || boundHint;
  return (
    <VStack align="stretch" spacing={4}>
      {banner && (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          {banner}
        </Alert>
      )}
      <FormControl isRequired={!isView} isInvalid={!isView && Boolean(errors.name)}>
        <FieldLabel variant={isView ? "inline" : undefined}>Application name</FieldLabel>
        {isView ? (
          <Text fontSize="md">{form.name || "—"}</Text>
        ) : (
          <>
            <Input
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
              placeholder={FIELD_HINTS.application.name.placeholder}
            />
            <FormErrorMessage>{errors.name}</FormErrorMessage>
            <FieldHint show={!errors.name}>{FIELD_HINTS.application.name.helper}</FieldHint>
          </>
        )}
      </FormControl>
      <FormControl>
        <FieldLabel variant={isView ? "inline" : undefined}>Description</FieldLabel>
        {isView ? (
          <Text fontSize="md">{form.description || "—"}</Text>
        ) : (
          <>
            <Textarea
              value={form.description}
              onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
              placeholder={FIELD_HINTS.application.description.placeholder}
              rows={3}
            />
            <FieldHint>{FIELD_HINTS.application.description.helper}</FieldHint>
          </>
        )}
      </FormControl>
      <FormControl>
        <FieldLabel variant={isView ? "inline" : undefined}>Domain</FieldLabel>
        {isView ? (
          <Text fontSize="md">{form.domain || "—"}</Text>
        ) : (
          <>
            <Input
              value={form.domain}
              onChange={(e) => setForm((prev) => ({ ...prev, domain: e.target.value }))}
              placeholder={FIELD_HINTS.application.domain.placeholder}
            />
            <FieldHint>{FIELD_HINTS.application.domain.helper}</FieldHint>
          </>
        )}
      </FormControl>
      {showBudget && isView ? (
        <FormControl>
          <FieldLabel variant="inline">Budget allocation</FieldLabel>
          <Text fontSize="md" fontWeight="semibold">
            {form.allocated_percentage === "" ? "—" : formatPct(Number(form.allocated_percentage))}
          </Text>
        </FormControl>
      ) : null}
      {showBudget && !isView ? (
        <FormControl isInvalid={Boolean(budgetError)}>
          <FieldLabel>Budget allocation</FieldLabel>
          <PercentageStepper
            value={form.allocated_percentage}
            onChange={(next) => {
              setBoundHint(null);
              setForm((prev) => ({ ...prev, allocated_percentage: next }));
            }}
            onBoundHit={(bound) => setBoundHint(percentageBoundMessage(bound))}
          />
          <FormErrorMessage>{budgetError}</FormErrorMessage>
          <FieldHint show={!budgetError}>
            {FIELD_HINTS.application.budget.helper} {remainingPct.toFixed(2)}% remaining.
            {budgetPreview != null ? ` ≈ ${formatSpendMoney(budgetPreview, currency)}` : ""}
          </FieldHint>
        </FormControl>
      ) : (
        <Text fontSize="sm" color="ink.500">
          Budget is managed separately — use Edit Budget on the row or above the list.
        </Text>
      )}
    </VStack>
  );
}
