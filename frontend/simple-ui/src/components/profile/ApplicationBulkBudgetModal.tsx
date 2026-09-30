import React, { useMemo } from "react";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  FormControl,
  Text,
  VStack,
} from "@chakra-ui/react";
import StandardModal from "../common/StandardModal";
import FormActions from "../common/FormActions";
import DataTable, { type DataTableColumn } from "../common/table";
import PercentageStepper, {
  type PercentageBound,
} from "../common/PercentageStepper";
import { FIELD_HINTS } from "../../config/fieldHints";
import { BUDGET_COPY, totalApplicationsOver100 } from "../../config/budgetMessages";
import { allocatedKeyFloorAmount } from "../../utils/applicationBudgetPreview";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import { InstitutionAllocationPanel } from "./applicationSurface";
import {
  BudgetAmountCell,
  formatBudgetMoney,
  formatBudgetPct,
} from "./budgetVisuals";
import type { BulkBudgetDraft } from "./hooks/useApplicationManagement";
import { BudgetFieldFeedback, bulkBudgetModalProps } from "./BudgetAllocationField";

function formatPct(value: number | null | undefined): string {
  if (value == null) return "—";
  const rounded = Math.round(value * 100) / 100;
  return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(2)}%`;
}

function parsePctInput(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : -1;
}

/** Institution room still assignable to this Application, in rupees. */
function applicationHeadroomAmount(
  row: BulkBudgetDraft,
  rows: BulkBudgetDraft[],
  tenantBudget: number,
): number | null {
  if (tenantBudget <= 0) return null;
  const othersPct = rows.reduce(
    (sum, other) =>
      other.application_id === row.application_id ? sum : sum + (other.resolvedPct ?? 0),
    0,
  );
  const maxPct = Math.max(0, 100 - othersPct);
  return Math.round(((tenantBudget * maxPct) / 100) * 100) / 100;
}

function hasUsageAmounts(row: BulkBudgetDraft): boolean {
  return (
    row.allocated_amount != null ||
    row.consumed_budget != null ||
    row.remaining_budget != null
  );
}

export default function ApplicationBulkBudgetModal({
  isOpen,
  onClose,
  isLoading,
  isSaving,
  banner,
  tenantBudget,
  institutionBudgetUnset,
  currency,
  liveTotalPct,
  rows,
  onRowFocus,
  onPctChange,
  onPctBoundHit,
  onSave,
  canSave,
}: {
  isOpen: boolean;
  onClose: () => void;
  isLoading: boolean;
  isSaving: boolean;
  banner: string | null;
  tenantBudget: number;
  institutionBudgetUnset: boolean;
  currency: string;
  liveTotalPct: number;
  rows: BulkBudgetDraft[];
  onRowFocus: (applicationId: string) => void;
  onPctChange: (applicationId: string, value: string) => void;
  onPctBoundHit: (applicationId: string, bound: PercentageBound) => void;
  onSave: () => void;
  canSave: boolean;
}) {
  const totalOver = liveTotalPct > 100 + 1e-6;
  const rowsRef = React.useRef(rows);
  rowsRef.current = rows;
  const tenantBudgetRef = React.useRef(tenantBudget);
  tenantBudgetRef.current = tenantBudget;

  const columns = useMemo<DataTableColumn<BulkBudgetDraft>[]>(
    () => [
      {
        id: "name",
        header: "Application",
        sortable: true,
        sortAccessor: (row) => row.name ?? "",
        cell: (row) => {
          const editable = row.status === "ACTIVE";
          return (
            <Box opacity={editable ? 1 : 0.75} minW={0} maxW="220px">
              <Text fontWeight="600" fontSize="sm" noOfLines={2} title={row.name}>
                {row.name}
              </Text>
              {!editable ? (
                <Badge mt={1} colorScheme="gray" fontSize="10px">
                  Inactive
                </Badge>
              ) : null}
            </Box>
          );
        },
      },
      {
        id: "allocated",
        header: "Allocated",
        sortable: true,
        sortAccessor: (row) => row.originalPct ?? -1,
        cell: (row) => (
          <BudgetAmountCell
            primary={formatBudgetPct(row.originalPct)}
            secondary={formatBudgetMoney(row.allocated_amount, currency)}
          />
        ),
      },
      {
        id: "consumed",
        header: "Consumed",
        sortable: true,
        sortAccessor: (row) => row.consumed_budget ?? row.consumed_percentage ?? -1,
        cell: (row) => {
          if (!hasUsageAmounts(row)) {
            if (row.rowError?.startsWith("Could not load")) {
              return (
                <Text fontSize="sm" color="red.500">
                  Load failed — refocus to retry
                </Text>
              );
            }
            return (
              <Text fontSize="sm" color="ink.400">
                {row.keysLoading ? BUDGET_COPY.loading : "Focus row to load keys"}
              </Text>
            );
          }
          return (
            <BudgetAmountCell
              primary={formatBudgetPct(row.consumed_percentage)}
              secondary={formatBudgetMoney(row.consumed_budget, currency)}
            />
          );
        },
      },
      {
        id: "remaining",
        header: "Remaining",
        sortable: true,
        sortAccessor: (row) => row.remaining_budget ?? -1,
        cell: (row) => (
          <BudgetAmountCell primary={formatBudgetMoney(row.remaining_budget, currency)} />
        ),
      },
      {
        id: "budgetPct",
        header: "Allocation",
        sortable: true,
        sortAccessor: (row) => parsePctInput(row.pctInput),
        cell: (row) => {
          const editable = row.status === "ACTIVE";
          return (
            <FormControl isInvalid={Boolean(row.rowError)}>
              <PercentageStepper
                variant="inline"
                value={row.pctInput}
                onChange={(next) => onPctChange(row.application_id, next)}
                onBoundHit={(bound) => onPctBoundHit(row.application_id, bound)}
                onFocus={() => onRowFocus(row.application_id)}
                isDisabled={!editable}
              />
              <BudgetFieldFeedback error={row.rowError} notice={row.inputNotice} />
            </FormControl>
          );
        },
      },
      {
        id: "range",
        header: "Allowed range",
        cell: (row) => {
          const maximum = applicationHeadroomAmount(
            row,
            rowsRef.current,
            tenantBudgetRef.current,
          );
          const minimum = Math.max(row.consumed_budget ?? 0, allocatedKeyFloorAmount(row.keys));
          const minimumPct =
            tenantBudgetRef.current > 0 ? (minimum / tenantBudgetRef.current) * 100 : null;
          return (
            <Text fontSize="12px" fontWeight="700" color="ink.800">
              {formatBudgetMoney(minimum, currency)}
              {minimumPct != null ? ` (${formatBudgetPct(minimumPct)})` : ""} – {formatBudgetMoney(maximum, currency)}
            </Text>
          );
        },
      },
      {
        id: "keyPreview",
        header: "Key preview",
        sortable: true,
        sortAccessor: (row) => row.keyPreviews.length,
        cell: (row) => {
          if (row.keysLoading) {
            return (
              <Text fontSize="xs" color="ink.500">
                Loading keys…
              </Text>
            );
          }
          if (row.keyPreviews.length === 0) {
            return (
              <Text fontSize="xs" color="ink.400">
                —
              </Text>
            );
          }
          return (
            <VStack align="stretch" spacing={1} maxW="220px">
              {row.keyPreviews.map((key) => (
                <Text
                  key={key.id}
                  fontSize="xs"
                  color={key.floorViolation ? "red.500" : "ink.600"}
                >
                  {key.key_name}: {formatPct(key.allocated_percentage)} ·{" "}
                  {formatSpendMoney(key.allocated_budget, currency)}
                </Text>
              ))}
            </VStack>
          );
        },
      },
    ],
    [currency, onPctChange, onPctBoundHit, onRowFocus],
  );

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title={BUDGET_COPY.bulkUpdateBudgets}
      {...bulkBudgetModalProps}
      footer={
        <FormActions
          submitLabel={BUDGET_COPY.saveAllChanges}
          onCancel={onClose}
          onSubmit={() => void onSave()}
          isLoading={isSaving}
          isDisabled={!canSave}
          mutedWhenDisabled
          loadingText={BUDGET_COPY.saving}
          justify="flex-end"
          pt={0}
        />
      }
    >
      <VStack align="stretch" spacing={4}>
        <Text fontSize="sm" color="ink.500">
          Adjust each application’s share of the institution budget. Only rows you change are saved.
        </Text>
        <InstitutionAllocationPanel
          allocatedPct={liveTotalPct}
          availablePct={Math.max(0, 100 - liveTotalPct)}
          institutionBudget={tenantBudget}
          currency={currency}
          overAllocated={totalOver}
          overMessage="Allocation exceeds the available institution budget."
        />

        {institutionBudgetUnset && (
          <Alert status="warning" borderRadius="md">
            <AlertIcon />
            {FIELD_HINTS.application.institutionBudgetNotSet}
          </Alert>
        )}

        {totalOver && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {totalApplicationsOver100(liveTotalPct)}
          </Alert>
        )}

        {banner && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {banner}
          </Alert>
        )}

        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.application_id}
          defaultSortKey="name"
          defaultSortDirection="asc"
          isLoading={isLoading}
          isEmpty={!isLoading && rows.length === 0}
          emptyMessage="No Applications to edit."
          asyncStateHeight="160px"
          borderRadius="md"
          theadBg="ink.50"
          cellPy={2}
          containerMt={0}
        />
      </VStack>
    </StandardModal>
  );
}
