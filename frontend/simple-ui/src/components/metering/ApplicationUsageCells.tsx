import { Box, Flex, HStack, Text } from "@chakra-ui/react";
import React from "react";
import {
  formatSpendMoney,
  spendBarColor,
  USAGE_SPEND_ACCENT,
} from "../../utils/usageSpendHelpers";

export function formatApplicationPct(n: number): string {
  return `${(Math.round(n * 100) / 100).toFixed(2)}%`;
}

export function AllocatedPctPill({ pct }: { pct: number }) {
  return (
    <Text
      as="span"
      display="inline-block"
      ml={2}
      fontSize="11.5px"
      fontWeight="bold"
      color={USAGE_SPEND_ACCENT}
      bg="#E9F0FD"
      px="7px"
      py="1px"
      borderRadius="full"
      verticalAlign="middle"
    >
      {formatApplicationPct(pct)}
    </Text>
  );
}

export function ApplicationSpendCell({
  spent,
  remaining,
  pctUsed,
  currency,
  hasBudget,
  noBudgetLabel,
}: {
  spent: number;
  remaining: number;
  pctUsed: number;
  currency: string;
  hasBudget: boolean;
  noBudgetLabel: string;
}) {
  if (!hasBudget) {
    return (
      <Text fontSize="12.5px" color="gray.500" fontStyle="italic">
        {noBudgetLabel}
      </Text>
    );
  }

  const fillPct = Math.min(Math.max(pctUsed, 0), 100);
  const visualFillPct = fillPct > 0 && fillPct < 2 ? 2 : fillPct;

  return (
    <Box minW="200px">
      <Flex justify="flex-end" fontSize="13px" fontWeight="bold" color="gray.800" mb="6px">
        {formatSpendMoney(spent, currency)}
      </Flex>
      <Box h="6px" borderRadius="6px" bg="#E4E9F3" overflow="hidden">
        <Box h="100%" w={`${visualFillPct}%`} bg={spendBarColor(pctUsed)} borderRadius="6px" />
      </Box>
      <Flex justify="space-between" fontSize="11.5px" color="gray.500" mt="6px">
        <Text>{formatApplicationPct(pctUsed)} used</Text>
        <Text>{formatSpendMoney(remaining, currency)} left</Text>
      </Flex>
    </Box>
  );
}

export function ApplicationRemainingCell({
  remaining,
  pctOfAllocation,
  currency,
  hasBudget,
  noBudgetLabel,
  ofAllocationLabel,
}: {
  remaining: number;
  pctOfAllocation: number;
  currency: string;
  hasBudget: boolean;
  noBudgetLabel?: string;
  ofAllocationLabel: string;
}) {
  if (!hasBudget) {
    return (
      <Text fontSize="12.5px" color="gray.500" fontStyle="italic">
        {noBudgetLabel ?? "—"}
      </Text>
    );
  }

  return (
    <Box>
      <Text fontSize="14px" fontWeight="bold" color="gray.800">
        {formatSpendMoney(remaining, currency)}
      </Text>
      <Text as="span" display="block" fontSize="11.5px" fontWeight="semibold" color="gray.500" mt="2px">
        {formatApplicationPct(pctOfAllocation)} {ofAllocationLabel}
      </Text>
    </Box>
  );
}

export function ApiKeyStatusBadge({ isActive }: { isActive: boolean }) {
  return (
    <Text
      as="span"
      display="inline-block"
      mt={1}
      fontSize="10.5px"
      fontWeight="bold"
      px="7px"
      py="1px"
      borderRadius="full"
      bg={isActive ? "#E7F6EC" : "#FBE9EE"}
      color={isActive ? "#2F9E44" : "#D6336C"}
    >
      {isActive ? "Active" : "Inactive"}
    </Text>
  );
}

export function SummaryPctPill({ label }: { label: string }) {
  return (
    <HStack spacing={0} mt="auto" pt={2}>
      <Text
        fontSize="10px"
        fontWeight="semibold"
        color="gray.500"
        bg="white"
        borderWidth="1px"
        borderColor="gray.200"
        px="7px"
        py="2px"
        borderRadius="full"
      >
        {label}
      </Text>
    </HStack>
  );
}
