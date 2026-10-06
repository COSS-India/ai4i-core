import { Box, HStack, Text } from "@chakra-ui/react";
import React from "react";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import { BUDGET_COPY } from "../../config/budgetMessages";

/** Reference budget dialogs use two-decimal percentages. */
export function formatBudgetPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(Math.round(value * 100) / 100).toFixed(2)}%`;
}

export function formatBudgetMoney(
  amount: number | null | undefined,
  currency = "INR",
): string {
  if (amount == null || !Number.isFinite(amount)) return "—";
  return formatSpendMoney(amount, currency);
}

/** Saved percent with rupees underneath, matching the reference table cells. */
export function BudgetAmountCell({
  primary,
  secondary,
  valueColor = "ink.800",
}: {
  primary: string;
  secondary?: string;
  valueColor?: string;
}) {
  return (
    <Box minW={0}>
      <Text fontSize="13px" fontWeight="700" color={valueColor} lineHeight="1.3">
        {primary}
      </Text>
      {secondary ? (
        <Text fontSize="11px" fontWeight="600" color="ink.500" mt="1px">
          {secondary}
        </Text>
      ) : null}
    </Box>
  );
}

export function RevokeBudgetBreakdown({
  status,
  allocated,
  consumed,
  unused,
  applicationName,
}: {
  status: "loading" | "ready" | "error";
  allocated?: number;
  consumed?: number;
  unused?: number;
  applicationName?: string;
}) {
  if (status === "error") {
    return (
      <Text fontSize="13px" color="ink.600" lineHeight="1.5">
        Budget usage could not be loaded. Allocated, consumed, and unused amounts are
        unavailable.
      </Text>
    );
  }

  const value = (amount: number | undefined) =>
    status === "loading" ? BUDGET_COPY.loading : formatBudgetMoney(amount);

  const rows: {
    label: string;
    hint?: string;
    value: string;
    tone: "total" | "plain" | "return";
  }[] = [
    { label: "Total Allocated", value: value(allocated), tone: "total" },
    { label: "Already Consumed", value: value(consumed), tone: "plain" },
    {
      label: "Unused",
      hint:
        status === "ready" && applicationName
          ? `Returns to ${applicationName}`
          : undefined,
      value: value(unused),
      tone: "return",
    },
  ];

  return (
    <Box borderWidth="1px" borderColor="ink.200" borderRadius="12px" overflow="hidden">
      {rows.map((row, index) => (
        <HStack
          key={row.label}
          justify="space-between"
          align="center"
          spacing={4}
          px="16px"
          py="12px"
          bg={row.tone === "total" ? "blue.50" : row.tone === "return" ? "green.50" : "white"}
          borderBottomWidth={index < rows.length - 1 ? "1px" : 0}
          borderColor="ink.200"
        >
          <Box minW={0}>
            <Text
              fontSize="12.5px"
              fontWeight={row.tone === "total" ? "700" : "600"}
              color={row.tone === "return" ? "green.700" : row.tone === "total" ? "ink.800" : "ink.600"}
            >
              {row.label}
            </Text>
            {row.hint ? (
              <Text fontSize="10.5px" fontWeight="600" color="green.600" mt="1px">
                {row.hint}
              </Text>
            ) : null}
          </Box>
          <Text
            fontSize="14.5px"
            fontWeight="800"
            color={row.tone === "return" ? "green.700" : "ink.800"}
            flexShrink={0}
          >
            {row.value}
          </Text>
        </HStack>
      ))}
    </Box>
  );
}
