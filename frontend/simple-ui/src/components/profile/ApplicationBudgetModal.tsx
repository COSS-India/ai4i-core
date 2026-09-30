import React from "react";
import { Alert, AlertIcon, Box, Text, VStack } from "@chakra-ui/react";
import StandardModal from "../common/StandardModal";
import FormActions from "../common/FormActions";
import { BUDGET_COPY, editBudgetTitle } from "../../config/budgetMessages";
import { FIELD_HINTS } from "../../config/fieldHints";
import { ApplicationBudgetFacts } from "./applicationSurface";
import { formatBudgetMoney, formatBudgetPct } from "./budgetVisuals";
import { BudgetAllocationField, singleBudgetModalProps } from "./BudgetAllocationField";
import { useApplicationManagement } from "./hooks/useApplicationManagement";

export default function ApplicationBudgetModal({
  mgr,
  currency,
}: {
  mgr: ReturnType<typeof useApplicationManagement>;
  currency: string;
}) {
  const usage = mgr.budgetUsageState === "ready" ? mgr.budgetUsage : null;
  const loading = mgr.budgetUsageState === "loading";
  const consumedPct =
    usage && mgr.tenantBudget > 0 ? (usage.consumed / mgr.tenantBudget) * 100 : null;
  const consumedLabel = loading
    ? BUDGET_COPY.loading
    : usage
      ? formatBudgetPct(consumedPct)
      : "—";
  const consumedSub = loading ? undefined : usage ? formatBudgetMoney(usage.consumed, currency) : "—";
  const maximumAmount =
    mgr.tenantBudget > 0 ? (mgr.budgetAvailable / 100) * mgr.tenantBudget : null;
  const rangeValue = loading
    ? BUDGET_COPY.loading
    : `${usage ? formatBudgetMoney(usage.consumed, currency) : "—"} – ${formatBudgetMoney(maximumAmount, currency)}`;
  const draftPct = Number(mgr.budgetDraft);
  const draftOk = mgr.budgetDraft.trim() !== "" && Number.isFinite(draftPct);
  const draftAmount =
    draftOk && mgr.tenantBudget > 0 ? (draftPct / 100) * mgr.tenantBudget : null;
  const allocatedAmount = usage ? usage.allocated : mgr.selected?.allocated_budget;
  const remainingAmount = usage ? usage.remaining : null;
  const remainingPct =
    remainingAmount != null && mgr.tenantBudget > 0
      ? (remainingAmount / mgr.tenantBudget) * 100
      : null;
  const remainingNegative = remainingAmount != null && remainingAmount < 0;
  const close = () => mgr.setBudgetOpen(false);

  return (
    <StandardModal
      isOpen={mgr.budgetOpen}
      onClose={close}
      title={editBudgetTitle(mgr.selected?.name)}
      {...singleBudgetModalProps}
      footer={
        <FormActions
          submitLabel={BUDGET_COPY.saveChanges}
          onCancel={close}
          onSubmit={() => void mgr.handleSaveBudget()}
          isLoading={mgr.isSaving}
          isDisabled={
            Boolean(mgr.budgetFieldError) ||
            mgr.institutionBudgetUnset ||
            mgr.selected?.status !== "ACTIVE" ||
            loading
          }
          mutedWhenDisabled
          loadingText={BUDGET_COPY.saving}
          justify="flex-end"
          pt={0}
        />
      }
    >
      <VStack align="stretch" spacing={4}>
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
        <Box>
          <Text fontSize="sm" fontWeight="600" color="ink.800" mb={2}>
            {BUDGET_COPY.currentBudget}
          </Text>
          <ApplicationBudgetFacts
            allocatedPct={mgr.selected?.allocated_percentage}
            allocatedAmount={allocatedAmount}
            consumedLabel={consumedLabel}
            consumedSub={consumedSub}
            remainingLabel={BUDGET_COPY.remaining}
            remainingValue={
              loading
                ? BUDGET_COPY.loading
                : remainingPct != null
                  ? formatBudgetPct(remainingPct)
                  : remainingAmount != null
                    ? formatBudgetMoney(remainingAmount, currency)
                    : "—"
            }
            remainingSub={
              loading || remainingAmount == null || remainingPct == null
                ? undefined
                : formatBudgetMoney(remainingAmount, currency)
            }
            remainingColor={
              remainingNegative ? "red.600" : remainingAmount != null ? "green.700" : "ink.800"
            }
            remainingSubColor={
              remainingNegative ? "red.600" : remainingAmount != null ? "green.700" : undefined
            }
            remainingNegative={remainingNegative}
            rangeLabel={rangeValue}
            currency={currency}
          />
        </Box>
        <BudgetAllocationField
          value={mgr.budgetDraft}
          onChange={mgr.setBudgetDraft}
          onBoundHit={mgr.onBudgetBoundHit}
          isDisabled={mgr.selected?.status !== "ACTIVE"}
          amountText={draftAmount != null ? formatBudgetMoney(draftAmount, currency) : "—"}
          fillPct={draftOk ? draftPct : 0}
          error={mgr.budgetFieldError}
          notice={mgr.budgetStepperHint}
          hint={FIELD_HINTS.application.budgetEdit.helper}
        />
      </VStack>
    </StandardModal>
  );
}
