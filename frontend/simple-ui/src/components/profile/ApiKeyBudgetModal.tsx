import React from "react";
import { Alert, AlertIcon, Box, Text, VStack } from "@chakra-ui/react";
import StandardModal from "../common/StandardModal";
import FormActions from "../common/FormActions";
import { type PercentageBound } from "../common/PercentageStepper";
import { ApplicationBudgetFacts } from "./applicationSurface";
import { formatBudgetMoney, formatBudgetPct } from "./budgetVisuals";
import {
  BUDGET_COPY,
  BUDGET_VALIDATION,
  editBudgetTitle,
  totalApiKeysExceeds100,
} from "../../config/budgetMessages";
import { FIELD_HINTS } from "../../config/fieldHints";
import { keyBudgetFigures, type KeyBudgetDraft } from "./hooks/useApiKeyBudgetEdit";
import { BudgetAllocationField, singleBudgetModalProps } from "./BudgetAllocationField";

export default function ApiKeyBudgetModal({
  isOpen,
  onClose,
  isLoading,
  isSaving,
  banner,
  applicationName,
  applicationBudget,
  applicationBudgetUnset,
  liveTotalPct,
  rows,
  focusedKeyId,
  focusedKeyName,
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
  applicationName: string;
  applicationBudget: number;
  applicationBudgetUnset: boolean;
  liveTotalPct: number;
  rows: KeyBudgetDraft[];
  focusedKeyId: number | null;
  focusedKeyName: string;
  onPctChange: (apiKeyId: number, value: string) => void;
  onPctBoundHit: (apiKeyId: number, bound: PercentageBound) => void;
  onSave: () => void;
  canSave: boolean;
}) {
  const currency = "INR";
  const row =
    focusedKeyId == null ? undefined : rows.find((item) => item.api_key_id === focusedKeyId);
  const keyName = row?.key_name || focusedKeyName || BUDGET_COPY.apiKeyFallback;
  const totalOver = liveTotalPct > 100 + 1e-6;
  const figures = row ? keyBudgetFigures(row, rows, applicationBudget) : null;
  const draftPct = row?.resolvedPct;
  const fieldError = row?.rowError || (totalOver ? totalApiKeysExceeds100(liveTotalPct) : null);
  const rangeLabel = isLoading
    ? BUDGET_COPY.loading
    : figures
      ? `${formatBudgetMoney(figures.minimum, currency)} – ${formatBudgetMoney(figures.maximum, currency)}`
      : "—";

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <Text noOfLines={2} pr={8} wordBreak="break-word" title={editBudgetTitle(keyName)}>
          {editBudgetTitle(keyName)}
        </Text>
      }
      {...singleBudgetModalProps}
      footer={
        <FormActions
          submitLabel={BUDGET_COPY.saveChanges}
          onCancel={onClose}
          onSubmit={onSave}
          isLoading={isSaving}
          isDisabled={!canSave || isLoading || !row}
          mutedWhenDisabled
          loadingText={BUDGET_COPY.saving}
          justify="flex-end"
          pt={0}
        />
      }
    >
      <VStack align="stretch" spacing={4}>
        <Text fontSize="sm" color="ink.600" noOfLines={2} wordBreak="break-word">
          {BUDGET_COPY.applicationPrefix}{" "}
          <Text as="span" fontWeight="600" color="ink.800">
            {isLoading ? BUDGET_COPY.loading : applicationName || "—"}
          </Text>
        </Text>
        {applicationBudgetUnset && !isLoading ? (
          <Alert status="warning" borderRadius="md">
            <AlertIcon />
            {BUDGET_VALIDATION.applicationBudgetUnavailable}
          </Alert>
        ) : null}
        {banner ? (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {banner}
          </Alert>
        ) : null}
        {!isLoading && focusedKeyId != null && !row ? (
          <Alert status="info" borderRadius="md">
            <AlertIcon />
            {BUDGET_COPY.inactiveKeyNotEditable}
          </Alert>
        ) : (
          <>
            <Box>
              <Text fontSize="sm" fontWeight="600" color="ink.800" mb={2}>
                {BUDGET_COPY.currentBudget}
              </Text>
              <ApplicationBudgetFacts
                allocatedPct={isLoading ? undefined : row?.originalPct}
                allocatedAmount={isLoading ? undefined : row?.originalAmount}
                allocatedLabel={isLoading ? BUDGET_COPY.loading : undefined}
                consumedLabel={isLoading ? BUDGET_COPY.loading : formatBudgetPct(row?.consumed_percentage)}
                consumedSub={
                  isLoading ? undefined : formatBudgetMoney(row?.consumed_budget, currency)
                }
                remainingValue={
                  isLoading ? BUDGET_COPY.loading : formatBudgetMoney(figures?.remaining, currency)
                }
                remainingSub={isLoading ? undefined : BUDGET_COPY.leftForThisKey}
                remainingColor={
                  figures?.remaining != null && figures.remaining >= 0 ? "green.700" : "ink.800"
                }
                rangeLabel={rangeLabel}
                currency={currency}
              />
            </Box>
            <BudgetAllocationField
              value={row?.pctInput ?? ""}
              onChange={(next) => {
                if (row) onPctChange(row.api_key_id, next);
              }}
              onBoundHit={(bound) => {
                if (row) onPctBoundHit(row.api_key_id, bound);
              }}
              isDisabled={!row || isLoading}
              amountText={formatBudgetMoney(row?.resolvedAmount, currency)}
              fillPct={draftPct != null && Number.isFinite(draftPct) ? draftPct : 0}
              error={fieldError}
              notice={row?.inputNotice}
              hint={FIELD_HINTS.apiKey.budget.helper}
            />
          </>
        )}
      </VStack>
    </StandardModal>
  );
}
