import React from "react";
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
  FormLabel,
  HStack,
  Heading,
  IconButton,
  Input,
  NumberDecrementStepper,
  NumberIncrementStepper,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  SimpleGrid,
  Text,
  Textarea,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { EditIcon, ViewIcon } from "@chakra-ui/icons";
import { FiPlus, FiRefreshCw, FiSliders } from "react-icons/fi";
import AdminDataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  TableSearchField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import StandardModal from "../common/StandardModal";
import ApplicationBulkBudgetModal from "./ApplicationBulkBudgetModal";
import FieldHint from "../common/FieldHint";
import InfoTip from "../common/InfoTip";
import { FIELD_HINTS } from "../../config/fieldHints";
import { BUDGET_VALIDATION } from "../../config/budgetMessages";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import type { Application } from "../../types/application";
import {
  useApplicationManagement,
  type ApplicationForm,
} from "./hooks/useApplicationManagement";

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
    <Card bg="#EDF2FB" borderColor="#E1E8F5" borderWidth="1px" boxShadow="none">
      <CardBody py={4} px={5}>
        <HStack spacing={1.5} mb={2} align="center">
          <Text
            fontSize="11.5px"
            fontWeight="700"
            color="blue.500"
            letterSpacing="0.5px"
            textTransform="uppercase"
          >
            {label}
          </Text>
          <InfoTip message={tooltip} />
        </HStack>
        <Text fontSize="23px" fontWeight="800" letterSpacing="-0.4px">
          {value}
        </Text>
        {subValue ? (
          <Text fontSize="12px" color="gray.500" mt={1}>
            {subValue}
          </Text>
        ) : null}
      </CardBody>
    </Card>
  );
}

function ViewLabelWithTip({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <HStack spacing={1.5} align="center">
      <Text fontSize="sm" color="gray.500">
        {label}
      </Text>
      <InfoTip message={tooltip} />
    </HStack>
  );
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

function PercentageStepper({
  value,
  onChange,
  min = 0,
  max = 100,
  onBoundHit,
  isDisabled = false,
}: {
  value: string;
  onChange: (next: string) => void;
  min?: number;
  max?: number;
  onBoundHit?: (bound: "min" | "max") => void;
  isDisabled?: boolean;
}) {
  const numeric = value.trim() === "" ? null : Number(value);
  const atMin = numeric != null && Number.isFinite(numeric) && numeric <= min + 1e-6;
  const atMax = numeric != null && Number.isFinite(numeric) && numeric >= max - 1e-6;

  return (
    <HStack maxW="180px" spacing={2} align="center">
      <NumberInput
        value={value}
        onChange={(next) => onChange(next)}
        min={min}
        max={max}
        step={1}
        precision={2}
        clampValueOnBlur
        bg="white"
        w="120px"
        isDisabled={isDisabled}
      >
        <NumberInputField />
        <NumberInputStepper>
          <NumberIncrementStepper
            cursor={atMax ? "not-allowed" : undefined}
            onClick={() => {
              if (atMax) onBoundHit?.("max");
            }}
          />
          <NumberDecrementStepper
            cursor={atMin || numeric == null ? "not-allowed" : undefined}
            onClick={() => {
              if (atMin || numeric == null) onBoundHit?.("min");
            }}
          />
        </NumberInputStepper>
      </NumberInput>
      <Text color="gray.500" fontWeight="semibold">
        %
      </Text>
    </HStack>
  );
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

  const columns: AdminTableColumn<Application>[] = [
    {
      id: "name",
      header: "Application",
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
            <Text fontWeight="700" fontSize="13px">
              {app.name}
            </Text>
            <Text fontSize="11px" color="gray.500" noOfLines={1}>
              {app.description || "No description"}
            </Text>
          </Box>
        </HStack>
      ),
    },
    {
      id: "domain",
      header: "Domain",
      cell: (app) => (
        <Badge
          variant="subtle"
          colorScheme="gray"
          borderWidth="1px"
          borderColor="gray.300"
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
      cell: (app) => (
        <Text fontWeight="700">{formatPct(app.allocated_percentage)}</Text>
      ),
    },
    {
      id: "status",
      header: "Status",
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
        <HStack spacing={0} justify="flex-end">
          <Tooltip label="View">
            <IconButton
              aria-label={`View ${app.name}`}
              icon={<ViewIcon />}
              size="sm"
              variant="ghost"
              color="gray.500"
              _hover={{ bg: "gray.100", color: "gray.800" }}
              onClick={() => mgr.openView(app)}
            />
          </Tooltip>
          <Tooltip label="Edit">
            <IconButton
              aria-label={`Edit ${app.name}`}
              icon={<EditIcon />}
              size="sm"
              variant="ghost"
              color="gray.500"
              _hover={{ bg: "gray.100", color: "gray.800" }}
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
                color="gray.500"
                _hover={{ bg: "blue.50", color: "blue.600" }}
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
        <Text fontSize="13.5px" color="gray.500" maxW="540px" lineHeight="1.5">
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
          <Button
            leftIcon={<FiPlus />}
            size="sm"
            colorScheme="blue"
            fontWeight="700"
            onClick={mgr.openCreate}
          >
            New Application
          </Button>
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

      <Box>
        <TableSearchField
          label="Application Name or Domain"
          placeholder={FIELD_HINTS.application.search.placeholder}
          helper={FIELD_HINTS.application.search.helper}
          value={mgr.searchInput}
          onChange={mgr.setSearchInput}
        />
      </Box>

      <AdminDataTable
        items={mgr.applications}
        columns={columns}
        getRowKey={(app) => app.application_id}
        onRowClick={mgr.openView}
        paginate="server"
        paginationPosition="top"
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
        tableContainerProps={{
          borderWidth: "1px",
          borderColor: "gray.300",
          borderRadius: "14px",
          overflow: "hidden",
        }}
      />

      <StandardModal
        isOpen={mgr.createOpen}
        onClose={() => mgr.setCreateOpen(false)}
        title="New Application"
        size="lg"
        footer={
          <HStack spacing={3}>
            <Button variant="ghost" onClick={() => mgr.setCreateOpen(false)}>
              Cancel
            </Button>
            <Button colorScheme="blue" isLoading={mgr.isSaving} onClick={() => void mgr.handleCreate()}>
              Create Application
            </Button>
          </HStack>
        }
      >
        <ApplicationIdentityFields
          form={mgr.form}
          setForm={mgr.setForm}
          errors={mgr.formErrors}
          banner={mgr.formBanner}
          showBudget
          remainingPct={mgr.remainingPct}
          budgetPreview={createPreview}
          currency={currency}
        />
      </StandardModal>

      <StandardModal
        isOpen={mgr.editOpen}
        onClose={() => mgr.setEditOpen(false)}
        title={mgr.selected ? `Edit ${mgr.selected.name}` : "Edit Application"}
        size="lg"
        footer={
          <HStack spacing={3}>
            <Button variant="ghost" onClick={() => mgr.setEditOpen(false)}>
              Cancel
            </Button>
            <Button colorScheme="blue" isLoading={mgr.isSaving} onClick={() => void mgr.handleEdit()}>
              Save changes
            </Button>
          </HStack>
        }
      >
        <ApplicationIdentityFields
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
        title="Application"
        size="lg"
        footer={
          <HStack spacing={3}>
            <Button variant="ghost" onClick={() => mgr.setViewOpen(false)}>
              Close
            </Button>
            {mgr.selected && (
              <Button
                colorScheme="blue"
                onClick={() => {
                  mgr.setViewOpen(false);
                  mgr.openEdit(mgr.selected!);
                }}
              >
                Edit
              </Button>
            )}
          </HStack>
        }
      >
        {mgr.selected && (
          <VStack align="stretch" spacing={4}>
            <Box>
              <HStack spacing={2} align="center" flexWrap="wrap">
                <Heading size="md">{mgr.selected.name}</Heading>
                <Badge colorScheme={mgr.selected.status === "ACTIVE" ? "green" : "gray"}>
                  {mgr.selected.status === "ACTIVE" ? "Active" : "Inactive"}
                </Badge>
              </HStack>
              {mgr.selected.domain ? (
                <Badge mt={2} variant="subtle">
                  {mgr.selected.domain}
                </Badge>
              ) : null}
            </Box>
            {mgr.selected.description ? (
              <Text color="gray.600">{mgr.selected.description}</Text>
            ) : null}
            <HStack justify="space-between">
              <Text fontSize="sm" color="gray.500">Budget allocation</Text>
              <Text fontWeight="semibold">{formatPct(mgr.selected.allocated_percentage)}</Text>
            </HStack>
            {mgr.selected.allocated_budget != null ? (
              <HStack justify="space-between">
                <Text fontSize="sm" color="gray.500">Budget amount</Text>
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
        title={mgr.selected ? `Edit Budget — ${mgr.selected.name}` : "Edit Budget"}
        size="lg"
        footer={
          <HStack spacing={3}>
            <Button variant="ghost" onClick={() => mgr.setBudgetOpen(false)}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              isLoading={mgr.isSaving}
              isDisabled={
                Boolean(mgr.budgetFieldError) ||
                mgr.institutionBudgetUnset ||
                mgr.selected?.status !== "ACTIVE"
              }
              onClick={() => void mgr.handleSaveBudget()}
            >
              Save changes
            </Button>
          </HStack>
        }
      >
        <VStack align="stretch" spacing={4}>
          <Box bg="blue.50" borderRadius="md" p={4}>
            <HStack justify="space-between" mb={2}>
              <HStack spacing={1.5} align="center">
                <Text fontSize="xs" fontWeight="bold" color="gray.500" textTransform="uppercase">
                  Institution Budget allocated
                </Text>
                <InfoTip message={FIELD_HINTS.application.tooltips.institutionBudgetAllocated} />
              </HStack>
              <Text fontWeight="bold">{formatPct(mgr.budgetLiveTotal)}</Text>
            </HStack>
            <Box h="8px" bg="gray.200" borderRadius="full" overflow="hidden">
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
            <FormLabel>{mgr.selected ? `${mgr.selected.name}’s Budget` : "Budget"}</FormLabel>
            <PercentageStepper
              value={mgr.budgetDraft}
              onChange={mgr.setBudgetDraft}
              min={mgr.budgetFloor > 0 ? mgr.budgetFloor : 0}
              max={mgr.budgetAvailable}
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
        onSave={() => void mgr.handleSaveBulkBudget()}
        canSave={mgr.bulkCanSave}
      />
    </VStack>
  );
}

function ApplicationIdentityFields({
  form,
  setForm,
  errors,
  banner,
  showBudget,
  remainingPct = 0,
  budgetPreview,
  currency = "INR",
}: {
  form: ApplicationForm;
  setForm: React.Dispatch<React.SetStateAction<ApplicationForm>>;
  errors: Record<string, string>;
  banner: string | null;
  showBudget: boolean;
  remainingPct?: number;
  budgetPreview?: number | null;
  currency?: string;
}) {
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
      <FormControl isRequired isInvalid={Boolean(errors.name)}>
        <FormLabel>Application name</FormLabel>
        <Input
          value={form.name}
          onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
          placeholder={FIELD_HINTS.application.name.placeholder}
        />
        <FormErrorMessage>{errors.name}</FormErrorMessage>
        <FieldHint show={!errors.name}>{FIELD_HINTS.application.name.helper}</FieldHint>
      </FormControl>
      <FormControl>
        <FormLabel>Description</FormLabel>
        <Textarea
          value={form.description}
          onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
          placeholder={FIELD_HINTS.application.description.placeholder}
          rows={3}
        />
        <FieldHint>{FIELD_HINTS.application.description.helper}</FieldHint>
      </FormControl>
      <FormControl>
        <FormLabel>Domain</FormLabel>
        <Input
          value={form.domain}
          onChange={(e) => setForm((prev) => ({ ...prev, domain: e.target.value }))}
          placeholder={FIELD_HINTS.application.domain.placeholder}
        />
        <FieldHint>{FIELD_HINTS.application.domain.helper}</FieldHint>
      </FormControl>
      {showBudget ? (
        <FormControl isInvalid={Boolean(budgetError)}>
          <FormLabel>Budget allocation</FormLabel>
          <PercentageStepper
            value={form.allocated_percentage}
            onChange={(next) => {
              setBoundHint(null);
              setForm((prev) => ({ ...prev, allocated_percentage: next }));
            }}
            min={0}
            max={Math.max(0, remainingPct)}
            onBoundHit={(bound) => {
              setBoundHint(
                bound === "min"
                  ? BUDGET_VALIDATION.budgetCannotBeNegative
                  : `Cannot exceed ${remainingPct.toFixed(2)}% still available.`,
              );
            }}
          />
          <FormErrorMessage>{budgetError}</FormErrorMessage>
          <FieldHint show={!budgetError}>
            {FIELD_HINTS.application.budget.helper} {remainingPct.toFixed(2)}% remaining.
            {budgetPreview != null ? ` ≈ ${formatSpendMoney(budgetPreview, currency)}` : ""}
          </FieldHint>
        </FormControl>
      ) : (
        <Text fontSize="sm" color="gray.500">
          Budget is managed separately — use Edit Budget on the row or above the list.
        </Text>
      )}
    </VStack>
  );
}
