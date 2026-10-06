import React, { useMemo } from "react";
import {
  Alert,
  AlertIcon,
  FormControl,
  Input,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import StandardModal from "../common/StandardModal";
import FormActions from "../common/FormActions";
import FieldLabel from "../common/FieldLabel";
import DataTable, { type DataTableColumn } from "../common/table";
import PercentageStepper, {
  type PercentageBound,
} from "../common/PercentageStepper";
import { FIELD_HINTS } from "../../config/fieldHints";
import { BUDGET_COPY, BUDGET_VALIDATION, totalApiKeysExceeds100 } from "../../config/budgetMessages";
import type { Application } from "../../types/application";
import { EntityIdentity, InstitutionAllocationPanel } from "./applicationSurface";
import {
  BudgetAmountCell,
  formatBudgetMoney,
  formatBudgetPct,
} from "./budgetVisuals";
import { keyBudgetFigures, type KeyBudgetDraft } from "./hooks/useApiKeyBudgetEdit";
import { BudgetFieldFeedback, bulkBudgetModalProps } from "./BudgetAllocationField";

function parseNumberInput(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : -1;
}

export default function ApiKeyBulkBudgetModal({
  isOpen,
  onClose,
  isLoading,
  isSaving,
  banner,
  applications,
  selectedApplicationId,
  onApplicationChange,
  applicationName,
  applicationBudget,
  applicationBudgetUnset,
  liveTotalPct,
  rows,
  onPctChange,
  onPctBoundHit,
  onAmountChange,
  onSave,
  canSave,
}: {
  isOpen: boolean;
  onClose: () => void;
  isLoading: boolean;
  isSaving: boolean;
  banner: string | null;
  applications: Application[];
  selectedApplicationId: string;
  onApplicationChange: (applicationId: string) => void;
  applicationName: string;
  applicationBudget: number;
  applicationBudgetUnset: boolean;
  liveTotalPct: number;
  rows: KeyBudgetDraft[];
  onPctChange: (apiKeyId: number, value: string) => void;
  onPctBoundHit: (apiKeyId: number, bound: PercentageBound) => void;
  onAmountChange: (apiKeyId: number, value: string) => void;
  onSave: () => void;
  canSave: boolean;
}) {
  const totalOver = liveTotalPct > 100 + 1e-6;
  const currency = "INR";
  const rowsRef = React.useRef(rows);
  rowsRef.current = rows;
  const applicationBudgetRef = React.useRef(applicationBudget);
  applicationBudgetRef.current = applicationBudget;

  const columns = useMemo<DataTableColumn<KeyBudgetDraft>[]>(
    () => [
      {
        id: "key",
        header: "Key",
        sortable: true,
        sortAccessor: (row) => row.key_name ?? "",
        cell: (row) => <EntityIdentity name={row.key_name || BUDGET_COPY.apiKeyFallback} />,
      },
      {
        id: "allocated",
        header: "Allocated",
        sortable: true,
        sortAccessor: (row) => row.originalPct ?? -1,
        cell: (row) => (
          <BudgetAmountCell
            primary={formatBudgetPct(row.originalPct)}
            secondary={formatBudgetMoney(row.originalAmount, currency)}
          />
        ),
      },
      {
        id: "consumed",
        header: "Consumed",
        sortable: true,
        sortAccessor: (row) => row.consumed_budget ?? row.consumed_percentage ?? -1,
        cell: (row) => (
          <BudgetAmountCell
            primary={formatBudgetPct(row.consumed_percentage)}
            secondary={formatBudgetMoney(row.consumed_budget, currency)}
          />
        ),
      },
      {
        id: "remaining",
        header: "Remaining",
        sortable: true,
        sortAccessor: (row) =>
          keyBudgetFigures(row, rowsRef.current, applicationBudgetRef.current).remaining ?? -1,
        cell: (row) => {
          const figures = keyBudgetFigures(
            row,
            rowsRef.current,
            applicationBudgetRef.current,
          );
          const remaining = figures.remaining;
          return (
            <BudgetAmountCell
              primary={formatBudgetMoney(remaining, currency)}
              valueColor={remaining != null && remaining > 0 ? "green.700" : "ink.800"}
            />
          );
        },
      },
      {
        id: "budgetPct",
        header: "Allocation",
        sortable: true,
        sortAccessor: (row) => parseNumberInput(row.pctInput),
        cell: (row) => (
          <FormControl isInvalid={Boolean(row.rowError)}>
            <PercentageStepper
              variant="inline"
              value={row.pctInput}
              onChange={(next) => onPctChange(row.api_key_id, next)}
              onBoundHit={(bound) => onPctBoundHit(row.api_key_id, bound)}
            />
            <BudgetFieldFeedback error={row.rowError} notice={row.inputNotice} />
          </FormControl>
        ),
      },
      {
        id: "budgetAmount",
        header: `Budget (${currency})`,
        sortable: true,
        sortAccessor: (row) => parseNumberInput(row.amountInput),
        cell: (row) => (
          <Input
            type="number"
            size="sm"
            w="120px"
            bg="ink.50"
            value={row.amountInput}
            onChange={(e) => onAmountChange(row.api_key_id, e.target.value)}
            min={row.consumed_budget ?? undefined}
            step={0.01}
            isDisabled={applicationBudgetUnset}
            placeholder={applicationBudgetUnset ? "—" : undefined}
          />
        ),
      },
      {
        id: "range",
        header: "Allowed range",
        cell: (row) => {
          const figures = keyBudgetFigures(
            row,
            rowsRef.current,
            applicationBudgetRef.current,
          );
          return (
            <Text fontSize="12px" fontWeight="700" color="ink.800">
              {formatBudgetMoney(figures.minimum, currency)} – {formatBudgetMoney(figures.maximum, currency)}
            </Text>
          );
        },
      },
    ],
    [onPctChange, onPctBoundHit, onAmountChange, applicationBudgetUnset],
  );

  const emptyMessage = !selectedApplicationId
    ? FIELD_HINTS.apiKey.bulkBudgetEdit.selectApplicationPrompt
    : FIELD_HINTS.apiKey.bulkBudgetEdit.empty;

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
        <FormControl maxW="280px">
          <FieldLabel>Application</FieldLabel>
          <Select
            placeholder={FIELD_HINTS.apiKey.bulkBudgetEdit.selectApplicationPlaceholder}
            value={selectedApplicationId}
            onChange={(e) => onApplicationChange(e.target.value)}
            bg="white"
          >
            {applications.map((app) => (
              <option key={app.application_id} value={app.application_id}>
                {app.name}
              </option>
            ))}
          </Select>
        </FormControl>

        {selectedApplicationId && (
          <InstitutionAllocationPanel
            context={{
              label: "Application budget",
              value: formatBudgetMoney(applicationBudget, currency),
              sub: applicationName || "This application",
            }}
            allocatedPct={liveTotalPct}
            availablePct={Math.max(0, 100 - liveTotalPct)}
            institutionBudget={applicationBudget}
            currency={currency}
            overAllocated={totalOver}
            allocatedCaption="assigned to keys"
            availableCaption="unassigned"
            overMessage="Total API key allocation cannot exceed 100% of this application's budget."
          />
        )}

        {applicationBudgetUnset && selectedApplicationId && (
          <Alert status="warning" borderRadius="md">
            <AlertIcon />
            {BUDGET_VALIDATION.applicationBudgetUnavailable}
          </Alert>
        )}

        {totalOver && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {totalApiKeysExceeds100(liveTotalPct)}
          </Alert>
        )}

        {banner && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {banner}
          </Alert>
        )}

        {selectedApplicationId ? (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => String(row.api_key_id)}
            defaultSortKey="key"
            defaultSortDirection="asc"
            isLoading={isLoading}
            isEmpty={!isLoading && rows.length === 0}
            emptyMessage={emptyMessage}
            asyncStateHeight="160px"
            borderRadius="md"
            theadBg="ink.50"
            cellPy={2}
            containerMt={0}
          />
        ) : (
          <Text color="ink.500" py={8} textAlign="center">
            {FIELD_HINTS.apiKey.bulkBudgetEdit.selectApplicationPrompt}
          </Text>
        )}
      </VStack>
    </StandardModal>
  );
}
