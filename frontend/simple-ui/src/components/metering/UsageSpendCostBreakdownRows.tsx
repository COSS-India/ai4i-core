import { Box, HStack, Td, Text, Tr } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { MeteringCostShare, TierTaskTypeUsage } from "../../types/usageSpend";
import { formatTokenCount } from "../../utils/llmTokenBreakdown";
import { formatSpendMoneyExact } from "../../utils/usageSpendHelpers";
import { TokenShareBar } from "./UsageSpendCells";

function visibleShares(shares: MeteringCostShare[] | null | undefined): MeteringCostShare[] {
  return (shares ?? []).filter((share) => share.key !== "cached_input" || share.units > 0);
}

const childTd = { borderColor: "gray.100", py: 2 } as const;

const figureLabel = {
  fontSize: "11px",
  color: "gray.500",
  fontWeight: "semibold",
} as const;

/**
 * LLM cost breakdown under a task-type row. `periodUsage.breakdown` is the
 * deployed split: units, cost, and costShare. Cached input is omitted when
 * its units are zero. The Total row is `periodUsage.units` / `periodUsage.cost`.
 * Figures span the usage and quota columns.
 */
export function UsageSpendCostBreakdownRows({
  task,
  currency,
  leadingColSpan,
}: Readonly<{
  task: TierTaskTypeUsage;
  currency: string;
  /** Columns before "Usage in period": task type, plus tier when grouped by tier. */
  leadingColSpan: number;
}>) {
  const copy = METERING.USAGE_SPEND;
  const shares = visibleShares(task.periodUsage.breakdown);
  const { periodUsage } = task;

  return (
    <>
      <Tr bg="gray.50">
        <Td colSpan={leadingColSpan} {...childTd} />
        <Td colSpan={2} {...childTd}>
          <HStack spacing={4}>
            <Text {...figureLabel} w="88px" textAlign="right">
              Tokens
            </Text>
            <Text {...figureLabel} flex="1">
              Share of usage cost
            </Text>
            <Text {...figureLabel} w="96px" textAlign="right">
              Usage cost
            </Text>
          </HStack>
        </Td>
      </Tr>
      {shares.map((share) => (
        <Tr key={share.key} bg="gray.50">
          <Td pl={10} colSpan={leadingColSpan} {...childTd}>
            <Text fontSize="13px" color="gray.700">
              {share.label}
            </Text>
          </Td>
          <Td colSpan={2} {...childTd}>
            <HStack spacing={4}>
              <Text fontSize="sm" color="gray.800" w="88px" textAlign="right">
                {formatTokenCount(share.units)}
              </Text>
              <TokenShareBar pct={share.costShare} />
              <Text fontSize="sm" color="gray.800" w="96px" textAlign="right">
                {formatSpendMoneyExact(share.cost, currency)}
              </Text>
            </HStack>
          </Td>
        </Tr>
      ))}
      <Tr bg="gray.50">
        <Td pl={10} colSpan={leadingColSpan} {...childTd}>
          <Text fontSize="13px" fontWeight="bold" color="gray.800">
            {copy.BREAKDOWN_TOTAL}
          </Text>
        </Td>
        <Td colSpan={2} {...childTd}>
          <HStack spacing={4}>
            <Text fontSize="sm" fontWeight="bold" color="gray.800" w="88px" textAlign="right">
              {formatTokenCount(periodUsage.units)}
            </Text>
            <Box flex="1" />
            <Text fontSize="sm" fontWeight="bold" color="gray.800" w="96px" textAlign="right">
              {formatSpendMoneyExact(periodUsage.cost, currency)}
            </Text>
          </HStack>
        </Td>
      </Tr>
    </>
  );
}
