import { ChevronRightIcon } from "@chakra-ui/icons";
import { Box, HStack, IconButton, Td, Text, Tr } from "@chakra-ui/react";
import React from "react";
import {
  formatSharePct,
  formatTokenCount,
  formatTokenUsageCost,
  type LlmTokenBreakdownView,
} from "../../utils/llmTokenBreakdown";
import { USAGE_SPEND_ACCENT } from "../../utils/usageSpendHelpers";
import { formatNativeConsumption } from "../../utils/meteringFormatters";

const childTd = { borderColor: "gray.100" } as const;

export function LlmExpandButton({
  label,
  isOpen,
  onToggle,
}: {
  label: string;
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <IconButton
      aria-label={label}
      aria-expanded={isOpen}
      icon={<ChevronRightIcon />}
      size="xs"
      variant="ghost"
      transform={isOpen ? "rotate(90deg)" : undefined}
      transition="transform 0.15s ease"
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
    />
  );
}

function TokenShareBar({ pct }: { pct: number | null }) {
  const fill = pct == null ? 0 : Math.min(Math.max(pct, 0), 100);
  const visualFill = fill > 0 && fill < 2 ? 2 : fill;
  return (
    <HStack spacing={3} flex="1" minW={0}>
      <Box flex="1" h="6px" borderRadius="full" bg="gray.200" overflow="hidden">
        <Box h="100%" w={`${visualFill}%`} bg={USAGE_SPEND_ACCENT} borderRadius="full" />
      </Box>
      <Text fontSize="sm" color="gray.600" minW="58px" textAlign="right">
        {pct == null ? "—" : formatSharePct(pct)}
      </Text>
    </HStack>
  );
}

/** Model drill-down: token count and its share of total tokens. */
export function ModelLlmTokenRows({
  breakdown,
  unitSuffix,
}: {
  breakdown: LlmTokenBreakdownView;
  unitSuffix?: string | null;
}) {
  return (
    <>
      {breakdown.categories.map((category) => (
        <Tr key={category.id} bg="gray.50">
          <Td pl={10} colSpan={4} {...childTd}>
            <Text fontSize="sm" color="gray.700">
              {category.label}
            </Text>
          </Td>
          <Td isNumeric {...childTd}>
            <Text fontSize="sm" color="gray.700">
              {formatNativeConsumption(category.tokens, unitSuffix)}
            </Text>
          </Td>
          <Td colSpan={2} {...childTd}>
            <TokenShareBar pct={category.sharePct} />
          </Td>
        </Tr>
      ))}
      <Tr bg="gray.50">
        <Td pl={10} colSpan={4} {...childTd}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.800">
            Total
          </Text>
        </Td>
        <Td isNumeric {...childTd}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.800">
            {formatNativeConsumption(breakdown.totalTokens, unitSuffix)}
          </Text>
        </Td>
        <Td colSpan={2} {...childTd} />
      </Tr>
    </>
  );
}

function costLabel(cost: number | null, currency: string): string {
  return cost == null ? "—" : formatTokenUsageCost(cost, currency);
}

/**
 * Institution drill-down: tokens, share of usage cost, and usage cost.
 * The parent row keeps the quota bar; these rows sit under it.
 */
export function InstitutionLlmTokenRows({
  breakdown,
  currency,
  leadingBlankCells = 0,
}: {
  breakdown: LlmTokenBreakdownView;
  currency: string;
  /** Blank cells before the usage column (the tier column, when shown). */
  leadingBlankCells?: number;
}) {
  const blankCells = (rowKey: string) =>
    Array.from({ length: leadingBlankCells }, (_, index) => (
      <Td key={`${rowKey}-blank-${index}`} {...childTd} />
    ));
  const headerSx = {
    fontSize: "11px",
    color: "gray.500",
    fontWeight: "semibold",
    letterSpacing: "0.02em",
  } as const;

  return (
    <>
      <Tr bg="gray.50">
        <Td {...childTd} />
        {blankCells("header")}
        <Td {...childTd}>
          <HStack spacing={4}>
            <Text {...headerSx} w="88px" textAlign="right">
              Tokens
            </Text>
            <Text {...headerSx} flex="1">
              Share of usage cost
            </Text>
            <Text {...headerSx} w="88px" textAlign="right">
              Usage cost
            </Text>
          </HStack>
        </Td>
      </Tr>
      {breakdown.categories.map((category) => (
        <Tr key={category.id} bg="gray.50">
          <Td pl={10} {...childTd}>
            <Text fontSize="sm" color="gray.700">
              {category.label}
            </Text>
          </Td>
          {blankCells(category.id)}
          <Td {...childTd}>
            <HStack spacing={4}>
              <Text fontSize="sm" color="gray.800" w="88px" textAlign="right">
                {formatTokenCount(category.tokens)}
              </Text>
              <TokenShareBar pct={category.sharePct} />
              <Text fontSize="sm" color="gray.800" w="88px" textAlign="right">
                {costLabel(category.cost, currency)}
              </Text>
            </HStack>
          </Td>
        </Tr>
      ))}
      <Tr bg="gray.50">
        <Td pl={10} {...childTd}>
          <Text fontSize="sm" fontWeight="semibold" color="gray.800">
            Total
          </Text>
        </Td>
        {blankCells("total")}
        <Td {...childTd}>
          <HStack spacing={4}>
            <Text fontSize="sm" fontWeight="semibold" color="gray.800" w="88px" textAlign="right">
              {formatTokenCount(breakdown.totalTokens)}
            </Text>
            <Box flex="1" />
            <Text fontSize="sm" fontWeight="semibold" color="gray.800" w="88px" textAlign="right">
              {costLabel(breakdown.totalCost, currency)}
            </Text>
          </HStack>
        </Td>
      </Tr>
    </>
  );
}
