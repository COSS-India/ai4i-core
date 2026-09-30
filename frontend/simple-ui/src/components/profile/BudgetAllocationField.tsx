import React from "react";
import { Box, Flex, FormControl, FormErrorMessage, Text } from "@chakra-ui/react";
import FieldHint from "../common/FieldHint";
import PercentageStepper, { type PercentageBound } from "../common/PercentageStepper";
import { BUDGET_COPY } from "../../config/budgetMessages";

/** Chrome shared by the Application and API key single-budget dialogs. */
export const singleBudgetModalProps = {
  size: "2xl" as const,
  scrollBehavior: "inside" as const,
  modalProps: { blockScrollOnMount: true },
  contentProps: { borderRadius: "16px", maxW: "640px", maxH: "88vh" },
  headerProps: { px: 6, pt: 5, pb: 3, fontSize: "17px", fontWeight: "800" },
  bodyProps: { px: 6, pt: 2, pb: 4 },
  footerProps: { px: 6, py: 4 },
};

/** Chrome shared by the Application and API key bulk-budget dialogs. */
export const bulkBudgetModalProps = {
  size: "6xl" as const,
  scrollBehavior: "inside" as const,
  modalProps: { blockScrollOnMount: true },
  contentProps: { borderRadius: "16px", maxH: "88vh" },
  headerProps: { px: 6, pt: 5, pb: 4, fontSize: "17px", fontWeight: "800" },
  bodyProps: { px: 6, py: 6 },
  footerProps: { px: 6, py: 4 },
};

export function BudgetFieldFeedback({
  error,
  notice,
  hint,
  mt = 1,
}: {
  error?: string | null;
  notice?: string | null;
  hint?: string;
  mt?: number;
}) {
  return (
    <>
      <FormErrorMessage mt={mt}>{error}</FormErrorMessage>
      {notice && !error ? (
        <Text mt={mt} fontSize="xs" color="ink.600">
          {notice} {BUDGET_COPY.previousValueKept}
        </Text>
      ) : null}
      {hint ? (
        <FieldHint show={!error && !notice}>{hint}</FieldHint>
      ) : null}
    </>
  );
}

/** Percentage stepper, synced rupee amount, and validation for one budget draft. */
export function BudgetAllocationField({
  value,
  onChange,
  onBoundHit,
  isDisabled = false,
  amountText,
  fillPct,
  error,
  notice,
  hint,
}: {
  value: string;
  onChange: (next: string) => void;
  onBoundHit?: (bound: PercentageBound) => void;
  isDisabled?: boolean;
  amountText: string;
  fillPct: number;
  error?: string | null;
  notice?: string | null;
  hint?: string;
}) {
  const invalid = Boolean(error);
  const fill = Math.max(0, Math.min(fillPct, 100));
  return (
    <FormControl isInvalid={invalid}>
      <Text fontSize="sm" fontWeight="600" color="ink.800" mb={2}>
        {BUDGET_COPY.newAllocation}
      </Text>
      <Flex
        align="center"
        justify="space-between"
        gap={4}
        px={4}
        py={3}
        bg="white"
        borderWidth="1px"
        borderColor={invalid ? "red.300" : "blue.200"}
        borderRadius="lg"
        flexWrap="wrap"
      >
        <PercentageStepper
          value={value}
          onChange={onChange}
          onBoundHit={onBoundHit}
          isDisabled={isDisabled}
        />
        <Box textAlign="right" minW="120px">
          <Text fontSize="xl" fontWeight="700" color="ink.800" letterSpacing="-0.02em" lineHeight="1.1">
            {amountText}
          </Text>
          <Text fontSize="xs" color="ink.500" mt={1}>
            {BUDGET_COPY.atThisPercentage}
          </Text>
        </Box>
      </Flex>
      <Box mt={3} h="6px" bg="ink.100" borderRadius="full" overflow="hidden" aria-hidden>
        <Box h="100%" w={`${fill}%`} bg={invalid ? "red.500" : "blue.500"} borderRadius="full" />
      </Box>
      <BudgetFieldFeedback error={error} notice={notice} hint={hint} mt={2} />
    </FormControl>
  );
}
